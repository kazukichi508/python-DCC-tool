import maya.cmds as mc
import os
import re
from functools import partial

from PySide6 import QtWidgets, QtCore, QtGui
from maya.app.general.mayaMixin import MayaQWidgetBaseMixin
import maya.mel as mel
from shiboken6 import wrapInstance
from maya import OpenMayaUI as omui




ATTRIBUTE_MAP = {
    "base_color": "baseColor",
    "metalness": "metalness",
    "specular": "specular",
    "specular_roughness": "specularRoughness",
    "transmission": "transmission",
    "opacity": "opacity"
}

LINEAR_WORKFLOW_TYPES = [
    "metalness", "specular", "specular_roughness", "transmission", "opacity", "normal", "displacement"
]

project_path = mc.workspace(q=True, rd=True)
source_images_folder = mc.workspace(fileRuleEntry='sourceImages')
TEX_ROOT_DIR = os.path.join(project_path, source_images_folder).replace("\\", "/")

def get_maya_main_window():
    """MayaのメインウィンドウをPySideのウィジェットとして取得する"""
    main_window_ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)

class MaterialAssignerWindow(MayaQWidgetBaseMixin, QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(MaterialAssignerWindow, self).__init__(parent)
        self.setWindowTitle("Material Assigner")
        self.setGeometry(100, 100, 450, 720) 
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        
        self.selection_script_job = None
        self.connection_buttons = {} 
        self._is_updating_ui = False 
        self.setup_ui()
        
        if not mc.pluginInfo("mtoa", query=True, loaded=True):
            mc.warning("Arnold Renderer (mtoa) is not loaded. Please load the plugin.")
            self.assign_button.setEnabled(False)
            self.status_label.setText("<font color='red'>Arnold (mtoa) is not loaded.</font>")
            
        self.populate_material_list()
        self.start_selection_monitor()
        self.update_selection_info()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout()

        selection_group = QtWidgets.QGroupBox("選択情報")
        selection_layout = QtWidgets.QVBoxLayout()
        
        material_selector_layout = QtWidgets.QHBoxLayout()
        material_selector_label = QtWidgets.QLabel("シーンのマテリアル:")
        self.material_selector_combo = QtWidgets.QComboBox()
        self.refresh_materials_button = QtWidgets.QPushButton("リスト更新")
        material_selector_layout.addWidget(material_selector_label)
        material_selector_layout.addWidget(self.material_selector_combo)
        material_selector_layout.addWidget(self.refresh_materials_button)
        
        self.selected_material_label = QtWidgets.QLabel("オブジェクトを選択してください")
        self.selected_material_label.setAlignment(QtCore.Qt.AlignCenter)
        self.selected_material_label.setStyleSheet("background-color: #2D3748; color: #FFFFFF; padding: 6px; border-radius: 4px; font-weight: bold;")
        
        selection_layout.addLayout(material_selector_layout)
        selection_layout.addWidget(self.selected_material_label)
        selection_group.setLayout(selection_layout)
        
        self.material_selector_combo.currentIndexChanged.connect(self.select_objects_from_material)
        self.refresh_materials_button.clicked.connect(self.populate_material_list)


        assign_group = QtWidgets.QGroupBox("マテリアル作成・割り当て")
        assign_layout = QtWidgets.QVBoxLayout()
        description_label = QtWidgets.QLabel(
            "ポリゴンオブジェクトを複数選択し、下のボタンをクリックしてください。<br>"
            "テクスチャの無いマテリアルを作成し、オブジェクトに割り当てます。"
        )
        description_label.setWordWrap(True)
        self.assign_button = QtWidgets.QPushButton("マテリアルを作成・割り当て")
        self.assign_button.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold; padding: 8px;")
        self.assign_button.clicked.connect(self.process_selection)
        assign_layout.addWidget(description_label)
        assign_layout.addWidget(self.assign_button)
        assign_group.setLayout(assign_layout)
        
        arnold_group = QtWidgets.QGroupBox("Arnold アトリビュート")
        arnold_layout = QtWidgets.QVBoxLayout()

        subdiv_layout = QtWidgets.QHBoxLayout()
        subdiv_label = QtWidgets.QLabel("Subdivision Iterations:")
        self.subdiv_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.subdiv_slider.setRange(0, 10)
        self.subdiv_line_edit = QtWidgets.QLineEdit("0")
        self.subdiv_line_edit.setFixedWidth(40)
        self.subdiv_line_edit.setValidator(QtGui.QIntValidator(0, 10))
        subdiv_layout.addWidget(subdiv_label)
        subdiv_layout.addWidget(self.subdiv_slider)
        subdiv_layout.addWidget(self.subdiv_line_edit)
        
        height_layout = QtWidgets.QHBoxLayout()
        height_label = QtWidgets.QLabel("Shape Disp. Height:")
        self.height_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.height_slider.setRange(0, 200) # 0.0 ~ 2.0
        self.height_line_edit = QtWidgets.QLineEdit("1.0")
        self.height_line_edit.setFixedWidth(40)
        self.height_line_edit.setValidator(QtGui.QDoubleValidator(0.0, 100.0, 2))
        height_layout.addWidget(height_label)
        height_layout.addWidget(self.height_slider)
        height_layout.addWidget(self.height_line_edit)

        arnold_layout.addLayout(subdiv_layout)
        arnold_layout.addLayout(height_layout)
        arnold_group.setLayout(arnold_layout)
        
        self.subdiv_slider.valueChanged.connect(self.update_subdiv_text)
        self.subdiv_line_edit.returnPressed.connect(self.update_subdiv_slider)
        self.subdiv_slider.sliderReleased.connect(self.apply_subdivision_iterations)
        
        self.height_slider.valueChanged.connect(self.update_height_text)
        self.height_line_edit.returnPressed.connect(self.update_height_slider)
        self.height_slider.sliderReleased.connect(self.apply_displacement_height)


        utility_group = QtWidgets.QGroupBox("ユーティリティ")
        utility_layout = QtWidgets.QVBoxLayout()
        
        utility_buttons_layout = QtWidgets.QHBoxLayout()
        self.invert_y_button = QtWidgets.QPushButton("Normal MapのInvert Yをトグル")
        self.invert_y_button.setStyleSheet("background-color: #6B7280; color: white; padding: 6px;")
        self.invert_y_button.clicked.connect(self.toggle_all_normal_invert_y)
        self.reload_button = QtWidgets.QPushButton("全テクスチャを再読込")
        self.reload_button.setStyleSheet("background-color: #6B7280; color: white; padding: 6px;")
        self.reload_button.clicked.connect(self.reload_all_textures)
        utility_buttons_layout.addWidget(self.invert_y_button)
        utility_buttons_layout.addWidget(self.reload_button)

        self.delete_unused_button = QtWidgets.QPushButton("未使用ノードを削除")
        self.delete_unused_button.setStyleSheet("background-color: #CF0202; color: white; padding: 6px;")
        self.delete_unused_button.clicked.connect(self.delete_unused_nodes)

        utility_layout.addLayout(utility_buttons_layout)
        utility_layout.addWidget(self.delete_unused_button)
        utility_group.setLayout(utility_layout)

        disconnect_group = QtWidgets.QGroupBox("テクスチャ接続の管理")
        disconnect_layout = QtWidgets.QGridLayout()
        
        all_texture_types = list(ATTRIBUTE_MAP.keys()) + ["normal", "displacement"]
        row, col = 0, 0
        for tex_type in all_texture_types:
            button = QtWidgets.QPushButton(f"{tex_type}: -")
            button.clicked.connect(partial(self.toggle_texture_connection_by_type, tex_type))
            disconnect_layout.addWidget(button, row, col)
            self.connection_buttons[tex_type] = button 
            col += 1
            if col > 1:
                col = 0
                row += 1
        disconnect_group.setLayout(disconnect_layout)

        self.status_label = QtWidgets.QLabel("Ready.")
        
        main_layout.addWidget(selection_group)
        main_layout.addWidget(assign_group)
        main_layout.addWidget(arnold_group)
        main_layout.addWidget(utility_group)
        main_layout.addWidget(disconnect_group)
        main_layout.addStretch(1)
        main_layout.addWidget(self.status_label)
        
        self.setLayout(main_layout)

    def start_selection_monitor(self):
        if not self.selection_script_job:
            self.selection_script_job = mc.scriptJob(event=["SelectionChanged", self.update_selection_info], protected=True)

    def stop_selection_monitor(self):
        if self.selection_script_job and mc.scriptJob(exists=self.selection_script_job):
            mc.scriptJob(kill=self.selection_script_job, force=True)
            self.selection_script_job = None

    def closeEvent(self, event):
        self.stop_selection_monitor()
        super(MaterialAssignerWindow, self).closeEvent(event)

    def update_selection_info(self):
        if self._is_updating_ui:
            return
        
        self._is_updating_ui = True
        try:
            shader = self.get_shader_from_selection()
            
            if shader:
                self.selected_material_label.setText(shader)
            else:
                selection = mc.ls(selection=True, head=1)
                if not selection:
                    self.selected_material_label.setText("オブジェクトを選択してください")
                else:
                    self.selected_material_label.setText("マテリアルが割り当てられていません")

            self.material_selector_combo.blockSignals(True)
            if shader:
                index = self.material_selector_combo.findText(shader)
                if index != -1:
                    self.material_selector_combo.setCurrentIndex(index)
            else:
                self.material_selector_combo.setCurrentIndex(0) 
            self.material_selector_combo.blockSignals(False)

            self.update_arnold_attributes_ui()
            self.update_connection_status_ui()
        finally:
            self._is_updating_ui = False

    def populate_material_list(self):
        self.material_selector_combo.blockSignals(True)
        current_selection = self.material_selector_combo.currentText()
        self.material_selector_combo.clear()
        
        shaders = mc.ls(type='aiStandardSurface')
        if not shaders:
            self.material_selector_combo.addItem("シーンにマテリアルがありません")
            self.material_selector_combo.setEnabled(False)
        else:
            self.material_selector_combo.addItems([""] + sorted(shaders))
            self.material_selector_combo.setEnabled(True)
            index = self.material_selector_combo.findText(current_selection)
            if index != -1:
                self.material_selector_combo.setCurrentIndex(index)
            
        self.material_selector_combo.blockSignals(False)
        self.update_selection_info()

    def select_objects_from_material(self):
        if self._is_updating_ui:
            return
            
        self._is_updating_ui = True
        try:
            shader = self.material_selector_combo.currentText()
            if not (shader and mc.objExists(shader)):
                mc.select(clear=True)
                return

            sg_nodes = mc.listConnections(shader, type='shadingEngine')
            if sg_nodes:
                members = mc.sets(sg_nodes[0], q=True)
                if members:
                    transforms_to_select = []
                    for member in members:
                        node_type = mc.nodeType(member)
                        if node_type in ['mesh', 'nurbsSurface', 'subdiv']:
                            parent = mc.listRelatives(member, parent=True, fullPath=True)
                            if parent:
                                transforms_to_select.append(parent[0])
                        elif node_type == 'transform':
                            transforms_to_select.append(member)
                    
                    if transforms_to_select:
                        mc.select(list(set(transforms_to_select)), replace=True)
                    else:
                        mc.select(clear=True)
        finally:
            self._is_updating_ui = False
            # 選択変更イベントが即座に発行されないことがあるため、手動でUIを更新
            self.update_selection_info()


    def update_arnold_attributes_ui(self):
        shape = self.get_selected_shape()
        
        if shape and mc.attributeQuery('aiSubdivIterations', node=shape, exists=True):
            self.subdiv_slider.setEnabled(True)
            self.subdiv_line_edit.setEnabled(True)
            current_iter = mc.getAttr(f"{shape}.aiSubdivIterations")
            self.subdiv_slider.blockSignals(True)
            self.subdiv_line_edit.blockSignals(True)
            self.subdiv_slider.setValue(current_iter)
            self.subdiv_line_edit.setText(str(current_iter))
            self.subdiv_slider.blockSignals(False)
            self.subdiv_line_edit.blockSignals(False)
        else:
            self.subdiv_slider.setEnabled(False)
            self.subdiv_line_edit.setEnabled(False)
            self.subdiv_line_edit.setText("-")

        if shape and mc.attributeQuery('aiDispHeight', node=shape, exists=True):
            self.height_slider.setEnabled(True)
            self.height_line_edit.setEnabled(True)
            current_height = mc.getAttr(f"{shape}.aiDispHeight")
            self.height_slider.blockSignals(True)
            self.height_line_edit.blockSignals(True)
            self.height_slider.setValue(int(current_height * 100))
            self.height_line_edit.setText(f"{current_height:.2f}")
            self.height_slider.blockSignals(False)
            self.height_line_edit.blockSignals(False)
        else:
            self.height_slider.setEnabled(False)
            self.height_line_edit.setEnabled(False)
            self.height_line_edit.setText("-")

    def update_connection_status_ui(self):
        shader = self.get_shader_from_selection()
        if not shader:
            for tex_type, button in self.connection_buttons.items():
                button.setText(f"{tex_type}: -")
                button.setStyleSheet("")
                button.setEnabled(False)
            return

        for tex_type, button in self.connection_buttons.items():
            is_connected = self._is_texture_connected(shader, tex_type)
            button.setEnabled(True)
            if is_connected:
                button.setText(f"{tex_type}: ON")
                button.setStyleSheet("background-color: #02B918; color: white;") # Green
            else:
                button.setText(f"{tex_type}: OFF")
                button.setStyleSheet("background-color: #6B7280; color: white;") # Red

    def get_selected_shape(self):
        selection = mc.ls(selection=True, head=1)
        if not selection: return None
        shapes = mc.listRelatives(selection[0], shapes=True, fullPath=True, type='mesh')
        return shapes[0] if shapes else None

    def get_shader_from_selection(self):
        shape = self.get_selected_shape()
        if not shape: return None
        sg_nodes = mc.listConnections(shape, type='shadingEngine')
        if not sg_nodes: return None
        shaders = mc.listConnections(f"{sg_nodes[0]}.surfaceShader")
        return shaders[0] if shaders else None
        
    def _is_texture_connected(self, shader, tex_type):
        full_attr = ""
        if tex_type == "normal":
            full_attr = f"{shader}.normalCamera"
        elif tex_type == "displacement":
            sg_nodes = mc.listConnections(shader, type='shadingEngine')
            if not sg_nodes: return False
            full_attr = f"{sg_nodes[0]}.displacementShader"
        else:
            attr_name = ATTRIBUTE_MAP.get(tex_type)
            if not attr_name: return False
            full_attr = f"{shader}.{attr_name}"
        
        return bool(mc.listConnections(full_attr, s=True, d=False))

    def update_subdiv_text(self, value):
        self.subdiv_line_edit.setText(str(value))

    def update_subdiv_slider(self):
        value = int(self.subdiv_line_edit.text())
        self.subdiv_slider.setValue(value)
        self.apply_subdivision_iterations()

    def update_height_text(self, value):
        self.height_line_edit.setText(f"{value / 100.0:.2f}")

    def update_height_slider(self):
        value = float(self.height_line_edit.text())
        self.height_slider.setValue(int(value * 100))
        self.apply_displacement_height()

    def apply_subdivision_iterations(self):
        value = self.subdiv_slider.value()
        shape = self.get_selected_shape()
        if not (shape and mc.objExists(shape) and mc.attributeQuery('aiSubdivIterations', node=shape, exists=True)):
            return
        mc.setAttr(f"{shape}.aiSubdivIterations", value)

    def apply_displacement_height(self):
        value = self.height_slider.value() / 100.0
        shape = self.get_selected_shape()
        if not (shape and mc.objExists(shape) and mc.attributeQuery('aiDispHeight', node=shape, exists=True)):
            return
        mc.setAttr(f"{shape}.aiDispHeight", value)


    def process_selection(self):
        selection = mc.ls(selection=True, long=True)

        if not selection:
            self.status_label.setText("<font color='red'>Error: No objects selected.</font>")
            mc.warning("No objects selected.")
            return

        valid_objects = []
        for sel in selection:
            shapes = mc.listRelatives(sel, shapes=True, type='mesh', fullPath=True)
            if shapes:
                valid_objects.append(sel)

        if not valid_objects:
            self.status_label.setText("<font color='orange'>Warning: No polygon mesh objects selected.</font>")
            mc.warning("No polygon mesh objects selected.")
            return

        self.status_label.setText("Processing...")
        QtWidgets.QApplication.processEvents() 

        created_count = 0
        assigned_count = 0
        for obj_path in valid_objects:
            obj_name = obj_path.split('|')[-1]
            try:
                is_created = self.create_and_assign_material(obj_path, obj_name)
                if is_created:
                    created_count += 1
                else:
                    assigned_count += 1
            except Exception as e:
                mc.warning(f"Failed to process material for {obj_name}: {e}")
        
        self.status_label.setText(f"<font color='green'>Success: {created_count} materials created, {assigned_count} assigned.</font>")
        self.populate_material_list()
        self.update_selection_info()

    def create_and_assign_material(self, obj_path, obj_name):
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', obj_name)
        shader_name = f"{clean_name}_material"
        sg_node = None
        is_new_material = False
        shader_node = None

        if mc.objExists(shader_name) and mc.nodeType(shader_name) == 'aiStandardSurface':
            print(f"Info: Existing shader '{shader_name}' found. Re-using it.")
            shader_node = shader_name
            connections = mc.listConnections(shader_node, d=True, s=False, type="shadingEngine")
            if connections:
                sg_node = connections[0]
        
        if sg_node is None:
            is_new_material = True
            
            unique_shader_name = shader_name
            count = 1
            while mc.objExists(unique_shader_name):
                unique_shader_name = f"{shader_name}{count}"
                count += 1
            
            print(f"Info: Creating new shader '{unique_shader_name}'.")
            shader_node = mc.shadingNode('aiStandardSurface', asShader=True, name=unique_shader_name)
            sg_node = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=f"{shader_node}_SG")
            mc.connectAttr(f'{shader_node}.outColor', f'{sg_node}.surfaceShader')
            
        if sg_node:
            mc.sets(obj_path, edit=True, forceElement=sg_node)
        else:
            mc.warning(f"Could not find or create a Shading Group for shader '{shader_name}'. Assignment failed.")
        
        return is_new_material

    def _connect_single_texture(self, shader_node, material_name, tex_type, obj_path):
        texture_dir = self._get_texture_directory(material_name)
        
        attr_name = ""
        if tex_type == "normal":
            attr_name = "normalCamera"
        elif tex_type == "displacement":
            sg_nodes = mc.listConnections(shader_node, type='shadingEngine')
            if not sg_nodes: return
            attr_name = f"{sg_nodes[0]}.displacementShader"
        else:
            attr_name = ATTRIBUTE_MAP.get(tex_type)
        
        if not attr_name: return
        
        full_attr_name = attr_name if '.' in attr_name else f"{shader_node}.{attr_name}"
        
        texture_path = self.find_texture_file(texture_dir, tex_type)
        if not texture_path:
            return

        file_node, _ = self._create_texture_file_node(material_name, tex_type, texture_path)
        
        try:
            if tex_type == "normal":
                normal_map_node = mc.shadingNode('aiNormalMap', asUtility=True, name=f"{material_name}_NRM")
                mc.connectAttr(f"{file_node}.outColor", f"{normal_map_node}.input")
                mc.connectAttr(f"{normal_map_node}.outValue", full_attr_name)
            elif tex_type == "displacement":
                disp_shader_node = mc.shadingNode('displacementShader', asShader=True, name=f"{material_name}_DISP")
                mc.connectAttr(f"{file_node}.outAlpha", f"{disp_shader_node}.displacement")
                mc.connectAttr(f"{disp_shader_node}.displacement", full_attr_name)
                shapes = mc.listRelatives(obj_path, shapes=True, fullPath=True)
                if shapes:
                    for shape in shapes:
                        mc.setAttr(f"{shape}.aiSubdivType", 1) # catclark
                        mc.setAttr(f"{shape}.aiSubdivIterations", self.subdiv_slider.value())
            elif tex_type == "base_color":
                mc.connectAttr(f"{file_node}.outColor", f"{shader_node}.{attr_name}", force=True)
            elif tex_type == "opacity":
                mc.connectAttr(f"{file_node}.outColor", f"{shader_node}.{attr_name}", force=True)
            else:
                mc.connectAttr(f"{file_node}.outAlpha", full_attr_name, force=True)
            
            print(f"Connected {texture_path} to {full_attr_name}")
        except Exception as e:
            print(f"Could not connect {file_node} to {full_attr_name}: {e}")

    def toggle_all_normal_invert_y(self):
        normal_nodes = mc.ls(type='aiNormalMap')
        if not normal_nodes:
            self.status_label.setText("<font color='orange'>No aiNormalMap nodes found in scene.</font>")
            return
        
        toggled_count = 0
        for node in normal_nodes:
            try:
                current_value = mc.getAttr(f"{node}.invertY")
                mc.setAttr(f"{node}.invertY", not current_value)
                toggled_count += 1
            except Exception as e:
                mc.warning(f"Could not toggle invertY for {node}: {e}")
        
        self.status_label.setText(f"<font color='blue'>Toggled invertY for {toggled_count} aiNormalMap nodes.</font>")

    def reload_all_textures(self):
        self.status_label.setText("Reloading all textures...")
        QtWidgets.QApplication.processEvents()

        all_shaders = mc.ls(type='aiStandardSurface')
        if not all_shaders:
            self.status_label.setText("<font color='orange'>No aiStandardSurface nodes found.</font>")
            return

        reloaded_count = 0
        for shader_node in all_shaders:
            sg_nodes = mc.listConnections(shader_node, type='shadingEngine')
            if not sg_nodes: continue
            assigned_geo = mc.listConnections(sg_nodes[0], type='mesh')
            if not assigned_geo: continue
            
            obj_path = mc.listRelatives(assigned_geo[0], parent=True, fullPath=True)[0]
            material_name = obj_path.split('|')[-1]
            clean_material_name = re.sub(r'[^a-zA-Z0-9_]', '_', material_name)

            self.cleanup_texture_connections(shader_node)
            self.connect_textures(shader_node, clean_material_name, obj_path)
            reloaded_count += 1
        
        self.status_label.setText(f"<font color='green'>Reloaded textures for {reloaded_count} materials.</font>")
        self.update_selection_info()

    def cleanup_texture_connections(self, shader_node):
        all_tex_types = list(ATTRIBUTE_MAP.keys()) + ["normal", "displacement"]
        for tex_type in all_tex_types:
            self._cleanup_single_connection(shader_node, tex_type)

    def _cleanup_single_connection(self, shader, tex_type):
        full_attr = ""
        if tex_type == "normal":
            full_attr = f"{shader}.normalCamera"
        elif tex_type == "displacement":
            sg_nodes = mc.listConnections(shader, type='shadingEngine')
            if sg_nodes:
                full_attr = f"{sg_nodes[0]}.displacementShader"
            else: return False
        else:
            attr_name = ATTRIBUTE_MAP.get(tex_type)
            if not attr_name: return False
            full_attr = f"{shader}.{attr_name}"

        connections = mc.listConnections(full_attr, s=True, d=False, plugs=False)
        if connections:
            history = mc.listHistory(connections[0])
            nodes_to_delete = set()
            for node in history:
                if mc.nodeType(node) in ['file', 'place2dTexture', 'aiNormalMap', 'bump2d', 'displacementShader']:
                    nodes_to_delete.add(node)
            
            if nodes_to_delete:
                mc.delete(list(nodes_to_delete))
                return True
        return False

    def toggle_texture_connection_by_type(self, tex_type):
        self.status_label.setText(f"Toggling '{tex_type}' connection...")
        QtWidgets.QApplication.processEvents()
        
        selection = mc.ls(selection=True, long=True)
        shader = self.get_shader_from_selection()
        
        if not shader:
            self.status_label.setText("<font color='orange'>No material selected to toggle.</font>")
            return

        is_connected = self._is_texture_connected(shader, tex_type)

        if is_connected:
            self._cleanup_single_connection(shader, tex_type)
        else:
            if selection:
                obj_path = selection[0]
                material_name = obj_path.split('|')[-1]
                clean_material_name = re.sub(r'[^a-zA-Z0-9_]', '_', material_name)
                self._connect_single_texture(shader, clean_material_name, tex_type, obj_path)
        
        if selection and mc.objExists(selection[0]):
            mc.select(selection, replace=True)
        
        self.update_selection_info()
        self.status_label.setText(f"<font color='blue'>Toggled {tex_type} connection.</font>")

    def delete_unused_nodes(self):
        self.status_label.setText("Deleting unused nodes...")
        QtWidgets.QApplication.processEvents()
        
        try:
            mel.eval('MLdeleteUnused();')
            self.status_label.setText("<font color='blue'>Deleted unused shading nodes.</font>")
            mc.warning("Unused shading nodes have been deleted.")
        except Exception as e:
            self.status_label.setText("<font color='red'>Failed to delete unused nodes.</font>")
            mc.warning(f"An error occurred while deleting unused nodes: {e}")


    def _create_texture_file_node(self, material_name, tex_type, texture_path):
        file_node_name = f"{material_name}_{tex_type}_FILE"
        p2d_node_name = f"{material_name}_{tex_type}_P2D"

        file_node = mc.shadingNode('file', asTexture=True, name=file_node_name)
        p2d_node = mc.shadingNode('place2dTexture', asUtility=True, name=p2d_node_name)
        
        attrs_to_connect = [
            "coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV",
            "stagger", "wrapU", "wrapV", "repeatUV", "offset", "rotateUV",
            "noiseUV", "vertexUvOne", "vertexUvTwo", "vertexUvThree",
            "vertexCameraOne", "outUV", "outUvFilterSize"
        ]
        uv_attr_map = {"outUV": "uvCoord"}

        for attr in attrs_to_connect:
            source_attr = attr
            dest_attr = uv_attr_map.get(attr, attr)
            try:
                mc.connectAttr(f"{p2d_node}.{source_attr}", f"{file_node}.{dest_attr}", force=True)
            except Exception as e:
                print(f"Could not connect {p2d_node}.{source_attr} to {file_node}.{dest_attr}: {e}")
        
        mc.setAttr(f"{file_node}.fileTextureName", texture_path, type="string")

        if "<UDIM>" in texture_path:
            mc.setAttr(f"{file_node}.uvTilingMode", 3)

        if tex_type in LINEAR_WORKFLOW_TYPES:
            mc.setAttr(f"{file_node}.colorSpace", "Raw", type="string")
        else:
            mc.setAttr(f"{file_node}.colorSpace", "sRGB", type="string")

        # Alpha is Luminanceを設定（グレースケールマップの場合）
        if tex_type in ["metalness", "specular", "specular_roughness", "transmission", "opacity", "displacement"]:
             mc.setAttr(f"{file_node}.alphaIsLuminance", True)

        return file_node, p2d_node

    def _get_texture_directory(self, material_name):
        specific_texture_dir = os.path.join(TEX_ROOT_DIR, material_name)
        if os.path.isdir(specific_texture_dir):
            return specific_texture_dir
        
        base_name = re.sub(r'(\d+)$', '', material_name)
        base_texture_dir = os.path.join(TEX_ROOT_DIR, base_name)
        return base_texture_dir

    def find_texture_file(self, texture_dir, texture_type):
        if not os.path.isdir(texture_dir):
            return None
        
        udim_pattern = re.compile(r'(.+?)[._](\d{4})\.(.+)$', re.IGNORECASE)
        
        try:
            filenames = os.listdir(texture_dir)
        except OSError:
            return None

        udim_sets = {}
        for filename in filenames:
            if os.path.isfile(os.path.join(texture_dir, filename)) and texture_type.lower() in filename.lower():
                match = udim_pattern.match(filename)
                if match:
                    base_name = match.group(1)
                    if base_name not in udim_sets:
                        udim_sets[base_name] = []
                    udim_sets[base_name].append(match.group(2))
        
        if udim_sets:
            best_base_name = next((b for b, t in udim_sets.items() if '1001' in t), list(udim_sets.keys())[0])
            original_filename = next((f for f in filenames if f.startswith(best_base_name)), f"{best_base_name}.{udim_sets[best_base_name][0]}.png")
            _, ext = os.path.splitext(original_filename)
            return os.path.join(texture_dir, f"{best_base_name}.<UDIM>{ext}").replace("\\", "/")

        single_files = [f for f in filenames if os.path.isfile(os.path.join(texture_dir, f)) and texture_type.lower() in f.lower() and not udim_pattern.search(f)]
        
        if not single_files:
            return None

        exact_match = next((f for f in single_files if os.path.splitext(f)[0].lower() == texture_type.lower()), None)
        if exact_match:
            return os.path.join(texture_dir, exact_match).replace("\\", "/")

        prefix_match = next((f for f in single_files if f.lower().startswith(texture_type.lower() + '_') or f.lower().startswith(texture_type.lower() + '.')), None)
        if prefix_match:
            return os.path.join(texture_dir, prefix_match).replace("\\", "/")
            
        return os.path.join(texture_dir, min(single_files, key=len)).replace("\\", "/")

material_assigner_window_instance = None

def show_material_assigner_window():
    global material_assigner_window_instance
    if material_assigner_window_instance is not None:
        try:
            material_assigner_window_instance.close()
            material_assigner_window_instance.deleteLater()
        except Exception as e:
            print(f"Error closing existing window: {e}")
    
    material_assigner_window_instance = MaterialAssignerWindow(parent=get_maya_main_window())
    material_assigner_window_instance.show()
    return material_assigner_window_instance

if __name__ == "__main__":
    show_material_assigner_window()

import hou
import os
import re
import voptoolutils
from PySide2 import QtWidgets, QtCore, QtGui
from pxr import Usd

TEXTURE_TYPES = [
    "base_color", "specular_roughness", "metalness",
    "normal", "transmission", "opacity", "displacement"
]
TEX_ROOT_DIR = os.path.join(hou.text.expandString("$JOB"), "tex").replace("\\", "/")

class MaterialBuilderWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(MaterialBuilderWindow, self).__init__(parent)
        self.setWindowTitle("USD Material Tools")
        self.setGeometry(100, 100, 500, 550)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.udim_state = {}
        self.setup_ui()
        self.populate_material_list()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        batch_group = QtWidgets.QGroupBox("選択ノードからの一括作成")
        batch_layout = QtWidgets.QVBoxLayout()
        description_label1 = QtWidgets.QLabel(
            "/stageでノードを複数選択し、下のボタンをクリックしてください。<br>"
            "選択ノードを元にマテリアルと割り当てを一括で自動生成します。"
        )
        description_label1.setWordWrap(True)
        self.create_button = QtWidgets.QPushButton("選択ノードからマテリアルと割り当てを作成")
        self.create_button.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold;")
        self.create_button.clicked.connect(self.create_materials_from_selection)
        batch_layout.addWidget(description_label1)
        batch_layout.addWidget(self.create_button)
        batch_group.setLayout(batch_layout)
        main_layout.addWidget(batch_group)
        single_add_group = QtWidgets.QGroupBox("単一マテリアルの追加")
        single_add_layout = QtWidgets.QHBoxLayout()
        single_add_label = QtWidgets.QLabel("マテリアル名:")
        self.material_name_edit = QtWidgets.QLineEdit("custom_mat")
        self.add_single_button = QtWidgets.QPushButton("追加")
        self.add_single_button.clicked.connect(self.add_single_material)
        single_add_layout.addWidget(single_add_label)
        single_add_layout.addWidget(self.material_name_edit)
        single_add_layout.addWidget(self.add_single_button)
        single_add_group.setLayout(single_add_layout)
        main_layout.addWidget(single_add_group)
        main_layout.addWidget(self.create_separator())
        selection_layout = QtWidgets.QHBoxLayout()
        selection_label = QtWidgets.QLabel("操作対象のマテリアル:")
        self.material_selector_combo = QtWidgets.QComboBox()
        self.material_selector_combo.setMinimumWidth(200)
        self.material_selector_combo.currentIndexChanged.connect(self.update_image_node_list)
        self.refresh_material_list_button = QtWidgets.QPushButton("リスト更新")
        self.refresh_material_list_button.clicked.connect(self.populate_material_list)
        selection_layout.addWidget(selection_label)
        selection_layout.addWidget(self.material_selector_combo)
        selection_layout.addWidget(self.refresh_material_list_button)
        main_layout.addLayout(selection_layout)
        controls_layout = QtWidgets.QHBoxLayout()
        self.udim_toggle_button = QtWidgets.QPushButton("UDIMパス切り替え")
        self.udim_toggle_button.clicked.connect(self.toggle_udim_paths)
        self.reload_textures_button = QtWidgets.QPushButton("テクスチャ検索・再読込")
        self.reload_textures_button.clicked.connect(self.reload_textures_for_selected_material)
        self.layout_stage_button = QtWidgets.QPushButton("ステージ全体を整理")
        self.layout_stage_button.clicked.connect(self.layout_all_stage_nodes)
        controls_layout.addWidget(self.udim_toggle_button)
        controls_layout.addWidget(self.reload_textures_button)
        controls_layout.addWidget(self.layout_stage_button)
        main_layout.addLayout(controls_layout)
        self.image_nodes_group = QtWidgets.QGroupBox("                                       テクスチャマップの接続 On/Off")
        self.image_nodes_layout = QtWidgets.QVBoxLayout(self.image_nodes_group)
        self.image_nodes_group.setLayout(self.image_nodes_layout)
        main_layout.addWidget(self.image_nodes_group)
        main_layout.addStretch(1)
        self.status_label = QtWidgets.QLabel("Ready.")
        main_layout.addWidget(self.status_label)
        self.setLayout(main_layout)

    def create_material_network(self, mat_lib_node, material_name):
        mat_subnet_node = voptoolutils._setupMtlXBuilderSubnet(subnet_node=None, destination_node=mat_lib_node, name=material_name, mask=voptoolutils.MTLX_TAB_MASK, folder_label='USD Material Builder', render_context="kma")
        if not mat_subnet_node: return None

        surface = mat_subnet_node.node('mtlxstandard_surface')
        image_nodes = {}
        texture_info = {"base_color": "color3", "specular_roughness": "float", "metalness": "float", "normal": "vector3", "transmission": "float", "opacity": "float", "displacement": "float"}
        material_texture_dir = self._get_texture_directory(material_name)

        for img_name, signature in texture_info.items():
            new_node = mat_subnet_node.createNode("mtlximage", img_name)
            image_nodes[img_name] = new_node
            new_node.parm("signature").set(signature)
            texture_path = self.find_texture_file(material_texture_dir, img_name)
            if texture_path: new_node.parm("file").set(texture_path)

        if "normal" in image_nodes:
            normalmap_node = mat_subnet_node.node('normalmap')
            if not normalmap_node: normalmap_node = mat_subnet_node.createNode('mtlxnormalmap', 'normalmap')
            normalmap_node.setInput(0, image_nodes["normal"])
            surface.setInput(surface.inputIndex('normal'), normalmap_node)

        if "displacement" in image_nodes:
            displacement_node = mat_subnet_node.node('mtlxdisplacement')
            if not displacement_node: displacement_node = mat_subnet_node.createNode('mtlxdisplacement', 'mtlxdisplacement')
            displacement_node.setInput(0, image_nodes["displacement"])
            if surface.inputIndex('displacementshader') != -1:
                surface.setInput(surface.inputIndex('displacementshader'), displacement_node)

        for img_name, node in image_nodes.items()
            if img_name not in ["normal", "displacement", "opacity"] and surface.inputIndex(img_name) != -1:
                surface.setInput(surface.inputIndex(img_name), node)

        mat_subnet_node.layoutChildren()
        return mat_subnet_node

    def layout_all_stage_nodes(self):
        self.status_label.setText("ステージノードを整理しています..."); QtWidgets.QApplication.processEvents()
        stage = hou.node('/stage')
        if not stage: self.status_label.setText("<font color='red'>エラー: /stage ノードが見つかりません。</font>"); return
        try: stage.layoutChildren(); self.status_label.setText("<font color='blue'>ステージ全体のノードを整理しました。</font>")
        except Exception as e: self.handle_error(e)
    def _get_texture_directory(self, material_name):
        specific_texture_dir = os.path.join(TEX_ROOT_DIR, material_name)
        if os.path.isdir(specific_texture_dir):
            print(f"情報: 具体的なテクスチャフォルダ '{specific_texture_dir}' を使用します。"); return specific_texture_dir
        base_name = re.sub(r'(\d+)$', '', material_name)
        base_texture_dir = os.path.join(TEX_ROOT_DIR, base_name)
        if base_name != material_name: print(f"情報: '{specific_texture_dir}' が見つからないため、基本フォルダ '{base_texture_dir}' を検索します。")
        return base_texture_dir
    def find_texture_file(self, texture_dir, texture_type):
        if not os.path.isdir(texture_dir): return None
        udim_pattern = re.compile(r'(.+?)[._](\d{4})\.(.+)$', re.IGNORECASE)
        udim_sets = {}
        for filename in os.listdir(texture_dir):
            if os.path.isfile(os.path.join(texture_dir, filename)) and texture_type.lower() in filename.lower():
                match = udim_pattern.match(filename)
                if match:
                    base_name = match.group(1)
                    if base_name not in udim_sets: udim_sets[base_name] = []
                    udim_sets[base_name].append(match.group(2))
        if udim_sets:
            best_base_name = next((b for b, t in udim_sets.items() if '1001' in t), list(udim_sets.keys())[0])
            original_filename = next((f for f in os.listdir(texture_dir) if f.startswith(best_base_name)), f"{best_base_name}.{udim_sets[best_base_name][0]}.png")
            _, ext = os.path.splitext(original_filename)
            return os.path.join(texture_dir, f"{best_base_name}_<UDIM>{ext}").replace("\\", "/")
        single_files = [f for f in os.listdir(texture_dir) if os.path.isfile(os.path.join(texture_dir, f)) and texture_type.lower() in f.lower() and not udim_pattern.search(f)]
        if not single_files: return None
        exact_match = next((f for f in single_files if os.path.splitext(f)[0].lower() == texture_type.lower()), None)
        if exact_match: return os.path.join(texture_dir, exact_match).replace("\\", "/")
        prefix_match = next((f for f in single_files if f.lower().startswith(texture_type.lower() + '_') or f.lower().startswith(texture_type.lower() + '.')), None)
        if prefix_match: return os.path.join(texture_dir, prefix_match).replace("\\", "/")
        return os.path.join(texture_dir, min(single_files, key=len)).replace("\\", "/")
    def _get_or_create_base_nodes(self, selected_nodes=None):
        stage = hou.node('/stage');
        if not stage: self.status_label.setText("<font color='red'>エラー: /stage ノードが見つかりません。</font>"); return None, None
        mat_lib_node = stage.node("materiallibrary")
        if not mat_lib_node:
            mat_lib_node = stage.createNode('materiallibrary', 'materiallibrary')
            if selected_nodes: top_node = min(selected_nodes, key=lambda node: node.position().y()); mat_lib_node.setInput(0, top_node)
            else: mat_lib_node.setPosition(hou.Vector2(0,0))
        assign_node = stage.node("assignmaterial")
        if not assign_node: assign_node = stage.createNode('assignmaterial', 'assignmaterial'); assign_node.setInput(0, mat_lib_node); assign_node.moveToGoodPosition()
        return mat_lib_node, assign_node
    def _update_assign_node(self, mat_lib_node, assign_node):
        all_materials_in_lib = self._get_material_nodes()
        assign_node.parm('nummaterials').set(len(all_materials_in_lib))
        for i, material_node in enumerate(all_materials_in_lib):
            parm_index = i + 1; prim_path = "/" + material_node.name()
            mat_usd_path = mat_lib_node.parm("matpathprefix").eval() + material_node.name()
            prim_pattern_parm = assign_node.parm(f'primpattern{parm_index}'); mat_path_parm = assign_node.parm(f'matspecpath{parm_index}')
            if prim_pattern_parm and mat_path_parm: prim_pattern_parm.set(prim_path); mat_path_parm.set(mat_usd_path)
    def create_materials_from_selection(self):
        self.create_button.setEnabled(False); self.status_label.setText("一括作成を開始します..."); QtWidgets.QApplication.processEvents()
        try:
            selected_nodes = hou.selectedNodes()
            if not selected_nodes or not all(isinstance(n, hou.LopNode) for n in selected_nodes): self.status_label.setText("<font color='red'>エラー: LOPネットワーク内のソースノードを1つ以上選択してください。</font>"); self.create_button.setEnabled(True); return
            mat_lib_node, assign_node = self._get_or_create_base_nodes(selected_nodes)
            if not mat_lib_node or not assign_node: self.create_button.setEnabled(True); return
            existing_names = [child.name() for child in self._get_material_nodes()]
            for source_node in selected_nodes:
                base_material_name = source_node.name(); unique_material_name = base_material_name; suffix = 1
                while unique_material_name in existing_names: unique_material_name = f"{base_material_name}{suffix}"; suffix += 1
                existing_names.append(unique_material_name)
                self.create_material_network(mat_lib_node, unique_material_name)
            self._update_assign_node(mat_lib_node, assign_node)
            self.status_label.setText(f"<font color='green'>成功: {len(selected_nodes)}個のマテリアルを作成・更新しました。</font>")
            self.populate_material_list()
        except Exception as e: self.handle_error(e)
        finally: self.create_button.setEnabled(True)
    def add_single_material(self):
        self.add_single_button.setEnabled(False); self.status_label.setText("単一マテリアルを追加中..."); QtWidgets.QApplication.processEvents()
        try:
            base_material_name = self.material_name_edit.text()
            if not base_material_name: self.status_label.setText("<font color='red'>エラー: マテリアル名を入力してください。</font>"); self.add_single_button.setEnabled(True); return
            mat_lib_node, assign_node = self._get_or_create_base_nodes()
            if not mat_lib_node or not assign_node: self.add_single_button.setEnabled(True); return
            existing_names = [child.name() for child in self._get_material_nodes()]
            unique_material_name = base_material_name; suffix = 1
            while unique_material_name in existing_names: unique_material_name = f"{base_material_name}{suffix}"; suffix += 1
            if self.create_material_network(mat_lib_node, unique_material_name):
                self._update_assign_node(mat_lib_node, assign_node)
                self.status_label.setText(f"<font color='green'>成功: マテリアル '{unique_material_name}' を追加しました。</font>")
                self.populate_material_list()
        except Exception as e: self.handle_error(e)
        finally: self.add_single_button.setEnabled(True)
    def reload_textures_for_selected_material(self):
        selected_mat_path = self.material_selector_combo.currentData()
        if not selected_mat_path: self.status_label.setText("<font color='red'>エラー: マテリアルが選択されていません。</font>"); return
        mat_subnet_node = hou.node(selected_mat_path)
        if not mat_subnet_node: return
        self.status_label.setText(f"'{mat_subnet_node.name()}'のテクスチャを検索・再読込中..."); QtWidgets.QApplication.processEvents()
        material_texture_dir = self._get_texture_directory(mat_subnet_node.name())
        updated_count = 0; image_node_count = 0
        for child in mat_subnet_node.children():
            if child.type().name() == "mtlximage":
                image_node_count += 1; texture_type = child.name()
                texture_path = self.find_texture_file(material_texture_dir, texture_type)
                file_parm = child.parm("file")
                if file_parm:
                    current_path = file_parm.eval()
                    if texture_path and texture_path != current_path:
                        file_parm.set(texture_path); print(f"情報: '{child.name()}' にパス '{texture_path}' を設定しました。"); updated_count += 1
                    elif texture_path and texture_path == current_path:
                        file_parm.set(texture_path); print(f"情報: '{child.name()}' のパス '{texture_path}' を再読み込みしました。"); updated_count += 1
        if updated_count > 0: self.status_label.setText(f"<font color='green'>成功: {updated_count}個のテクスチャパスを更新しました。</font>")
        elif image_node_count > 0: self.status_label.setText(f"<font color='orange'>警告: '{os.path.basename(material_texture_dir)}'のフォルダに更新可能なテクスチャは見つかりませんでした。</font>")
        else: self.status_label.setText(f"<font color='orange'>警告: マテリアル内にmtlximageノードがありません。</font>")
        hou.ui.triggerUpdate()
    def handle_error(self, e):
        error_message = f"エラー: {str(e)}"; self.status_label.setText(f"<font color='red'>{error_message}</font>")
        hou.ui.displayMessage(f"処理中にエラーが発生しました:\n{e}", severity=hou.severityType.Error)
    def create_separator(self):
        line = QtWidgets.QFrame(); line.setFrameShape(QtWidgets.QFrame.HLine); line.setFrameShadow(QtWidgets.QFrame.Sunken); return line
    def closeEvent(self, event):
        global _material_builder_window_instance;
        if _material_builder_window_instance == self: _material_builder_window_instance = None
        super(MaterialBuilderWindow, self).closeEvent(event)
    def _get_material_nodes(self):
        stage = hou.node('/stage');
        if not stage: return []
        mat_lib_node = stage.node('materiallibrary');
        if not mat_lib_node: return []
        return [child for child in mat_lib_node.children() if child.isSubNetwork()]
    def populate_material_list(self):
        current_selection = self.material_selector_combo.currentData()
        self.material_selector_combo.clear(); material_builders = self._get_material_nodes()
        if not material_builders:
            self.material_selector_combo.addItem("--- No Materials Found ---"); self.udim_toggle_button.setEnabled(False); self.reload_textures_button.setEnabled(False); self.layout_stage_button.setEnabled(False)
        else:
            for node in sorted(material_builders, key=lambda n: n.name()): self.material_selector_combo.addItem(node.name(), node.path())
            self.udim_toggle_button.setEnabled(True); self.reload_textures_button.setEnabled(True); self.layout_stage_button.setEnabled(True)
            index = self.material_selector_combo.findData(current_selection)
            if index != -1: self.material_selector_combo.setCurrentIndex(index)
        self.update_image_node_list()
    def update_image_node_list(self):
        while self.image_nodes_layout.count():
            child = self.image_nodes_layout.takeAt(0)
            if child.widget(): child.widget().deleteLater()
        selected_mat_path = self.material_selector_combo.currentData()
        if not selected_mat_path: self.reload_textures_button.setEnabled(False); self.layout_stage_button.setEnabled(False); return
        mat_subnet_node = hou.node(selected_mat_path)
        if not mat_subnet_node or not mat_subnet_node.isSubNetwork(): self.reload_textures_button.setEnabled(False); self.layout_stage_button.setEnabled(False); return
        self.reload_textures_button.setEnabled(True); self.layout_stage_button.setEnabled(True)
        image_nodes = [child for child in mat_subnet_node.children() if child.type().name() == "mtlximage"]
        for child in sorted(image_nodes, key=lambda n: n.name()):
            h_layout = QtWidgets.QHBoxLayout(); label = QtWidgets.QLabel(f"{child.name()}:"); label.setFixedWidth(120); h_layout.addWidget(label)
            toggle_button = QtWidgets.QPushButton(); toggle_button.setFixedWidth(80); toggle_button.setProperty("node_path", child.path())
            is_connected = self.is_image_node_connected(child)
            toggle_button.setText("無効化" if is_connected else "有効化"); toggle_button.setStyleSheet("background-color: #4ADE80;" if is_connected else "background-color: #F87171;"); toggle_button.clicked.connect(self.toggle_image_node_connection)
            h_layout.addWidget(toggle_button); h_layout.addStretch(1); self.image_nodes_layout.addLayout(h_layout)
    def is_image_node_connected(self, image_node):
        mat_subnet_node = image_node.parent(); surface_node = mat_subnet_node.node('mtlxstandard_surface')
        if not surface_node: return False
        image_type = image_node.name()
        if image_type == "normal": normalmap_node = mat_subnet_node.node('normalmap'); return normalmap_node and surface_node.input(surface_node.inputIndex('normal')) == normalmap_node
        else:
            input_idx = surface_node.inputIndex(image_type)
            if input_idx != -1: return surface_node.input(input_idx) == image_node
        return False
    def toggle_image_node_connection(self):
        sender_button = self.sender(); image_node_path = sender_button.property("node_path"); image_node = hou.node(image_node_path)
        if not image_node: return
        mat_subnet_node = image_node.parent(); surface_node = mat_subnet_node.node('mtlxstandard_surface')
        if not surface_node: return
        image_type = image_node.name(); is_connected = self.is_image_node_connected(image_node)
        if is_connected:
            if image_type == "normal": surface_node.setInput(surface_node.inputIndex('normal'), None)
            else: surface_node.setInput(surface_node.inputIndex(image_type), None)
        else:
            if image_type == "normal":
                normalmap_node = mat_subnet_node.node('normalmap')
                if not normalmap_node: normalmap_node = mat_subnet_node.createNode('mtlxnormalmap', 'normalmap')
                if normalmap_node.input(0) != image_node: normalmap_node.setInput(0, image_node)
                surface_node.setInput(surface_node.inputIndex('normal'), normalmap_node)
            else: surface_node.setInput(surface_node.inputIndex(image_type), image_node)
        self.update_image_node_list(); mat_subnet_node.layoutChildren()
    def toggle_udim_paths(self):
        selected_mat_path = self.material_selector_combo.currentData()
        if not selected_mat_path: return
        mat_subnet_node = hou.node(selected_mat_path)
        if not mat_subnet_node: return
        mat_path = mat_subnet_node.path(); is_udim = self.udim_state.get(mat_path, False)
        for child in mat_subnet_node.children():
            if child.type().name() == "mtlximage":
                file_parm = child.parm("file");
                if not file_parm: continue
                current_path = file_parm.eval()
                if not current_path:
                    material_texture_dir = self._get_texture_directory(mat_subnet_node.name())
                    found_path = self.find_texture_file(material_texture_dir, child.name())
                    if found_path: file_parm.set(found_path); current_path = found_path
                    else: continue
                if is_udim:
                    new_path = re.sub(r'[_.]<UDIM>', '', current_path)
                    if new_path == current_path: new_path = re.sub(r'%\(UDIM\)d', '1001', new_path)
                    file_parm.set(new_path)
                else:
                    dir_path, base_filename = os.path.split(current_path); name_without_ext, ext = os.path.splitext(base_filename)
                    cleaned_name = re.sub(r'[_.]\d{4}$', '', name_without_ext)
                    udim_filename = f"{cleaned_name}_<UDIM>{ext}"; new_path = os.path.join(dir_path, udim_filename).replace("\\", "/")
                    file_parm.set(new_path)
        self.udim_state[mat_path] = not is_udim
        new_state_str = "UDIM" if not is_udim else "Original"; self.status_label.setText(f"<font color='blue'>パスを {new_state_str} に切り替えました。</font>")

_material_builder_window_instance = None
def show_material_builder_creator_window():
    global _material_builder_window_instance
    if _material_builder_window_instance is not None:
        try: _material_builder_window_instance.close(); _material_builder_window_instance.deleteLater()
        except Exception: pass
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    houdini_main_window = hou.ui.mainQtWindow()
    _material_builder_window_instance = MaterialBuilderWindow(parent=houdini_main_window)
    _material_builder_window_instance.show()
    _material_builder_window_instance.raise_(); _material_builder_window_instance.activateWindow()

show_material_builder_creator_window()

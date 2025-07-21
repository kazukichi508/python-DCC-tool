# -*- coding: utf-8 -*-
"""
Maya Material & Texture Manager

選択したオブジェクト名に基づいてArnoldマテリアルを作成・割り当て、
テクスチャの自動接続や各種ユーティリティ機能を提供するMaya用ツール。

主な機能:
- 選択オブジェクトに基づいたマテリアルの自動作成と割り当て
- シーン内のマテリアル一覧表示と、関連オブジェクトの選択
- テクスチャ検索パスの設定と履歴管理（自動保存）、テクスチャの一括リロード
- テクスチャタイプごとの自動接続・切断（UDIM対応）
- Arnold関連アトリビュート（Subdivision, Displacement）のインタラクティブな調整
- ユーティリティ機能（未使用ノード削除、Normal Map一括トグル、Subdivision一括設定）

バージョン: 2.8
最終更新日: 2025-07-21
作者: Gemini
"""

import maya.cmds as mc
import maya.mel as mel
import os
import re
from functools import partial

# Maya 2024 / 2025 以降のバージョンに対応するため、PySide6を使用
from PySide6 import QtWidgets, QtCore, QtGui
from maya.app.general.mayaMixin import MayaQWidgetBaseMixin
from shiboken6 import wrapInstance
from maya import OpenMayaUI as omui


# --- グローバル定数と設定 ---

# 接続するテクスチャタイプとシェーダのアトリビュート名を定義
ATTRIBUTE_MAP = {
    "base_color": "baseColor",
    "metalness": "metalness",
    "specular": "specular",
    "specular_roughness": "specularRoughness",
    "transmission": "transmission",
    "opacity": "opacity"
}

# リニアワークフローで処理すべきテクスチャタイプ
LINEAR_WORKFLOW_TYPES = [
    "metalness", "specular", "specular_roughness", "transmission", "opacity", "normal", "displacement"
]

# optionVar用のキー
OPTION_VAR_KEY = "MAYA_MATERIAL_ASSIGNER_SAVED_PATHS"


def get_maya_main_window():
    """MayaのメインウィンドウをPySideのウィジェットとして取得する"""
    main_window_ptr = omui.MQtUtil.mainWindow()
    if main_window_ptr is None:
        raise RuntimeError("Mayaのメインウィンドウが見つかりません。")
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)

class MaterialTextureManagerWindow(MayaQWidgetBaseMixin, QtWidgets.QWidget):
    """
    マテリアルの作成、割り当て、テクスチャ接続、各種ユーティリティ機能を統合したUIウィンドウクラス。
    """
    def __init__(self, parent=None):
        super(MaterialTextureManagerWindow, self).__init__(parent)
        self.setWindowTitle("Material & Texture Manager")
        self.resize(450, 400)
        # 標準的なリサイズ可能なウィンドウとして設定
        self.setWindowFlags(QtCore.Qt.Window)
        
        self.selection_script_job = None
        self.connection_buttons = {} 
        self._is_updating_ui = False # UI更新中の再帰呼び出しを防ぐフラグ

        self.setup_ui()
        
        # Arnoldがロードされているか確認
        if not mc.pluginInfo("mtoa", query=True, loaded=True):
            mc.warning("Arnold Renderer (mtoa) is not loaded. Please load the plugin.")
            self.assign_button.setEnabled(False)
            self.status_label.setText("<font color='red'>Arnold (mtoa) is not loaded.</font>")
        
        # UI表示後の初期化処理
        self.load_saved_paths()
        self.populate_material_list()
        self.start_selection_monitor()
        self.update_selection_info() # 初期選択状態を反映

    def setup_ui(self):
        """UIの部品を作成し、ウィンドウに配置する"""
        # UI全体をスクロール可能にするための構造
        top_layout = QtWidgets.QVBoxLayout(self)
        top_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)

        scroll_content_widget = QtWidgets.QWidget()
        scroll_area.setWidget(scroll_content_widget)
        
        main_layout = QtWidgets.QVBoxLayout(scroll_content_widget)
        main_layout.setContentsMargins(9, 9, 9, 9)

        # --- 選択情報セクション ---
        selection_group = QtWidgets.QGroupBox("選択情報")
        selection_layout = QtWidgets.QVBoxLayout()
        
        material_selector_layout = QtWidgets.QHBoxLayout()
        material_selector_label = QtWidgets.QLabel("シーンのマテリアル:")
        self.material_selector_combo = QtWidgets.QComboBox()
        self.refresh_materials_button = QtWidgets.QPushButton("リスト更新")
        self.refresh_materials_button.setToolTip("シーン内のaiStandardSurfaceマテリアルリストを更新します。")
        material_selector_layout.addWidget(material_selector_label)
        material_selector_layout.addWidget(self.material_selector_combo)
        material_selector_layout.addWidget(self.refresh_materials_button)
        
        self.selected_material_label = QtWidgets.QLabel("オブジェクトを選択してください")
        self.selected_material_label.setAlignment(QtCore.Qt.AlignCenter)
        self.selected_material_label.setStyleSheet("background-color: #2D3748; color: #FFFFFF; padding: 6px; border-radius: 4px; font-weight: bold;")
        
        selection_layout.addLayout(material_selector_layout)
        selection_layout.addWidget(self.selected_material_label)
        selection_group.setLayout(selection_layout)

        # --- マテリアル作成セクション ---
        assign_group = QtWidgets.QGroupBox("マテリアル作成・割り当て")
        assign_layout = QtWidgets.QVBoxLayout()
        description_label = QtWidgets.QLabel(
            "ポリゴンオブジェクトを複数選択し、下のボタンをクリックしてください。<br>"
            "オブジェクト名に基づいたマテリアルを作成し、オブジェクトに割り当てます。"
        )
        description_label.setWordWrap(True)
        self.assign_button = QtWidgets.QPushButton("マテリアルを作成・割り当て")
        self.assign_button.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold; padding: 8px;")
        assign_layout.addWidget(description_label)
        assign_layout.addWidget(self.assign_button)
        assign_group.setLayout(assign_layout)

        # --- テクスチャ検索パス設定セクション ---
        path_group = QtWidgets.QGroupBox("テクスチャ検索パス設定")
        path_layout = QtWidgets.QVBoxLayout()

        path_input_layout = QtWidgets.QHBoxLayout()
        self.custom_path_combo = QtWidgets.QComboBox()
        self.custom_path_combo.setEditable(True)
        self.custom_path_combo.setToolTip("テクスチャを検索するルートフォルダを指定します。\n入力完了後、自動で履歴に保存されます。")
        self.browse_button = QtWidgets.QPushButton("参照...")
        
        self.reload_button = QtWidgets.QPushButton("全テクスチャを再読込")
        self.reload_button.setStyleSheet("background-color: #6B7280; color: white; padding: 6px;")
        self.reload_button.setToolTip("シーン内の全てのfileノードのテクスチャをリロードします。")

        path_input_layout.addWidget(self.custom_path_combo)
        path_input_layout.addWidget(self.browse_button)
        path_input_layout.addWidget(self.reload_button)

        self.active_path_label = QtWidgets.QLabel("アクティブパス: ")
        self.active_path_label.setWordWrap(True)
        self.active_path_label.setStyleSheet("font-size: 9pt; color: #B0B0B0;")

        path_layout.addLayout(path_input_layout)
        path_layout.addWidget(self.active_path_label)
        path_group.setLayout(path_layout)
        
        # --- テクスチャ接続の管理セクション ---
        connection_group = QtWidgets.QGroupBox("テクスチャ接続の管理")
        connection_layout = QtWidgets.QGridLayout()
        
        all_texture_types = list(ATTRIBUTE_MAP.keys()) + ["normal", "displacement"]
        row, col = 0, 0
        for tex_type in all_texture_types:
            button = QtWidgets.QPushButton(f"{tex_type}: -")
            button.setToolTip(f"{tex_type} テクスチャの接続をトグルします。")
            button.clicked.connect(partial(self.toggle_texture_connection_by_type, tex_type))
            connection_layout.addWidget(button, row, col)
            self.connection_buttons[tex_type] = button
            col += 1
            if col > 1:
                col, row = 0, row + 1
        connection_group.setLayout(connection_layout)

        # --- Arnold アトリビュートセクション ---
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
        self.height_slider.setRange(0, 200) # 0.0 to 2.0
        self.height_line_edit = QtWidgets.QLineEdit("1.0")
        self.height_line_edit.setFixedWidth(40)
        self.height_line_edit.setValidator(QtGui.QDoubleValidator(0.0, 100.0, 2))
        height_layout.addWidget(height_label)
        height_layout.addWidget(self.height_slider)
        height_layout.addWidget(self.height_line_edit)

        arnold_layout.addLayout(subdiv_layout)
        arnold_layout.addLayout(height_layout)
        arnold_group.setLayout(arnold_layout)

        # --- ユーティリティセクション ---
        utility_group = QtWidgets.QGroupBox("ユーティリティ")
        utility_layout = QtWidgets.QVBoxLayout()
        
        # ★★★ 変更点: 新しいボタンを追加 ★★★
        self.set_subdiv_button = QtWidgets.QPushButton("Set Default Subdivision")
        self.set_subdiv_button.setStyleSheet("background-color: #6B7280; color: white; padding: 6px;")
        self.set_subdiv_button.setToolTip("選択したメッシュのSubdivisionを有効化し、\nIterations=2, Type=Catclarkに設定します。")
        
        self.invert_y_button = QtWidgets.QPushButton("Normal MapのInvert Yをトグル")
        self.invert_y_button.setStyleSheet("background-color: #6B7280; color: white; padding: 6px;")
        
        self.delete_unused_button = QtWidgets.QPushButton("未使用ノードを削除")
        self.delete_unused_button.setStyleSheet("background-color: #CF0202; color: white; padding: 6px;")

        utility_layout.addWidget(self.set_subdiv_button)
        utility_layout.addWidget(self.invert_y_button)
        utility_layout.addWidget(self.delete_unused_button)
        utility_group.setLayout(utility_layout)
        
        # --- レイアウトへの追加 ---
        main_layout.addWidget(selection_group)
        main_layout.addWidget(assign_group)
        main_layout.addWidget(path_group)
        main_layout.addWidget(connection_group)
        main_layout.addWidget(arnold_group)
        main_layout.addWidget(utility_group)
        main_layout.addStretch(1)
        
        # --- ステータスラベル（スクロールエリアの外） ---
        self.status_label = QtWidgets.QLabel("Ready.")
        self.status_label.setStyleSheet("padding: 2px 9px;") # 見栄えのためのパディング

        # トップレイアウトにスクロールエリアとステータスラベルを配置
        top_layout.addWidget(scroll_area)
        top_layout.addWidget(self.status_label)

        # --- シグナル接続 ---
        self.material_selector_combo.currentIndexChanged.connect(self.select_objects_from_material)
        self.refresh_materials_button.clicked.connect(self.populate_material_list)
        self.assign_button.clicked.connect(self.process_selection)

        self.browse_button.clicked.connect(self.browse_for_path)
        self.custom_path_combo.lineEdit().editingFinished.connect(self.add_current_path_to_history)
        self.custom_path_combo.currentTextChanged.connect(self.update_active_path_display)
        
        self.subdiv_slider.valueChanged.connect(self.update_subdiv_text)
        self.subdiv_line_edit.returnPressed.connect(self.update_subdiv_slider)
        self.subdiv_slider.sliderReleased.connect(self.apply_subdivision_iterations)
        
        self.height_slider.valueChanged.connect(self.update_height_text)
        self.height_line_edit.returnPressed.connect(self.update_height_slider)
        self.height_slider.sliderReleased.connect(self.apply_displacement_height)

        # ★★★ 変更点: 新しいボタンのシグナルを接続 ★★★
        self.set_subdiv_button.clicked.connect(self.set_default_subdivision)
        self.invert_y_button.clicked.connect(self.toggle_all_normal_invert_y)
        self.reload_button.clicked.connect(self.reload_all_textures)
        self.delete_unused_button.clicked.connect(self.delete_unused_nodes)

    # --------------------------------------------------------------------------
    # イベントとUI更新
    # --------------------------------------------------------------------------

    def start_selection_monitor(self):
        """Mayaの選択変更イベントを監視するscriptJobを開始する"""
        if not self.selection_script_job:
            self.selection_script_job = mc.scriptJob(event=["SelectionChanged", self.update_selection_info], protected=True)

    def stop_selection_monitor(self):
        """scriptJobを停止する"""
        if self.selection_script_job and mc.scriptJob(exists=self.selection_script_job):
            mc.scriptJob(kill=self.selection_script_job, force=True)
            self.selection_script_job = None

    def closeEvent(self, event):
        """ウィンドウが閉じられるときにscriptJobを停止する"""
        self.stop_selection_monitor()
        super(MaterialTextureManagerWindow, self).closeEvent(event)

    def update_selection_info(self):
        """選択されたオブジェクトに基づいてUI全体を更新する"""
        if self._is_updating_ui: return
        
        self._is_updating_ui = True
        try:
            shader = self.get_shader_from_selection()
            
            # 選択マテリアルラベルの更新
            if shader:
                self.selected_material_label.setText(shader)
            else:
                selection = mc.ls(selection=True, head=1)
                self.selected_material_label.setText("マテリアルがありません" if selection else "オブジェクトを選択してください")

            # マテリアル選択ドロップダウンの更新
            self.material_selector_combo.blockSignals(True)
            if shader:
                index = self.material_selector_combo.findText(shader)
                if index != -1:
                    self.material_selector_combo.setCurrentIndex(index)
            else:
                self.material_selector_combo.setCurrentIndex(0)
            self.material_selector_combo.blockSignals(False)

            # 各UIセクションの更新
            self.update_arnold_attributes_ui()
            self.update_connection_status_ui()
        finally:
            self._is_updating_ui = False

    def populate_material_list(self):
        """シーン内のaiStandardSurfaceマテリアルをリストアップしてUIに表示する"""
        self.material_selector_combo.blockSignals(True)
        current_selection = self.material_selector_combo.currentText()
        self.material_selector_combo.clear()
        
        shaders = mc.ls(type='aiStandardSurface')
        if not shaders:
            self.material_selector_combo.addItem("シーンにマテリアルがありません")
            self.material_selector_combo.setEnabled(False)
        else:
            self.material_selector_combo.addItems([""] + sorted(shaders)) # 先頭に空の選択肢を追加
            self.material_selector_combo.setEnabled(True)
            index = self.material_selector_combo.findText(current_selection)
            if index != -1:
                self.material_selector_combo.setCurrentIndex(index)
                
        self.material_selector_combo.blockSignals(False)
        # self.update_selection_info() # 無限ループを避けるため、ここでは呼ばない

    def select_objects_from_material(self):
        """UIのドロップダウンからマテリアルが選択されたときに、対応するオブジェクトを選択する"""
        if self._is_updating_ui: return
            
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
                        # 常にトランスフォームノードを選択する
                        if mc.nodeType(member) in ['mesh', 'nurbsSurface', 'subdiv']:
                            parent = mc.listRelatives(member, parent=True, fullPath=True)
                            if parent: transforms_to_select.append(parent[0])
                        elif mc.nodeType(member) == 'transform':
                            transforms_to_select.append(member)
                    
                    if transforms_to_select:
                        mc.select(list(set(transforms_to_select)), replace=True)
                    else:
                        mc.select(clear=True)
        finally:
            self._is_updating_ui = False
            # 選択変更イベントが即座に発行されないことがあるため、手動でUIを更新
            mc.evalDeferred(self.update_selection_info)

    def update_arnold_attributes_ui(self):
        """選択オブジェクトに基づいてArnold関連UIを更新する"""
        shape = self.get_selected_shape()
        
        # Subdivision UIの更新
        has_subdiv = bool(shape and mc.attributeQuery('aiSubdivIterations', node=shape, exists=True))
        self.subdiv_slider.setEnabled(has_subdiv)
        self.subdiv_line_edit.setEnabled(has_subdiv)
        if has_subdiv:
            current_iter = mc.getAttr(f"{shape}.aiSubdivIterations")
            self.subdiv_slider.blockSignals(True)
            self.subdiv_line_edit.blockSignals(True)
            self.subdiv_slider.setValue(current_iter)
            self.subdiv_line_edit.setText(str(current_iter))
            self.subdiv_slider.blockSignals(False)
            self.subdiv_line_edit.blockSignals(False)
        else:
            self.subdiv_line_edit.setText("-")

        # Displacement Height UIの更新
        has_disp = bool(shape and mc.attributeQuery('aiDispHeight', node=shape, exists=True))
        self.height_slider.setEnabled(has_disp)
        self.height_line_edit.setEnabled(has_disp)
        if has_disp:
            current_height = mc.getAttr(f"{shape}.aiDispHeight")
            self.height_slider.blockSignals(True)
            self.height_line_edit.blockSignals(True)
            self.height_slider.setValue(int(current_height * 100))
            self.height_line_edit.setText(f"{current_height:.2f}")
            self.height_slider.blockSignals(False)
            self.height_line_edit.blockSignals(False)
        else:
            self.height_line_edit.setText("-")

    def update_connection_status_ui(self):
        """選択中のマテリアルのテクスチャ接続状態をUIボタンに反映させる"""
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
                button.setStyleSheet("background-color: #6B7280; color: white;") # Gray

    # --------------------------------------------------------------------------
    # ヘルパー関数 (オブジェクト情報取得)
    # --------------------------------------------------------------------------

    def get_selected_shape(self):
        """選択中のオブジェクトから最初のメッシュシェイプノードを取得する"""
        selection = mc.ls(selection=True, head=1)
        if not selection: return None
        shapes = mc.listRelatives(selection[0], shapes=True, fullPath=True, type='mesh')
        return shapes[0] if shapes else None

    def get_shader_from_selection(self):
        """選択中のオブジェクトからシェーダノードを取得する"""
        shape = self.get_selected_shape()
        if not shape: return None
        sg_nodes = mc.listConnections(shape, type='shadingEngine')
        if not sg_nodes: return None
        # surfaceShaderの接続を優先的に取得
        shaders = mc.listConnections(f"{sg_nodes[0]}.surfaceShader")
        if shaders: return shaders[0]
        # Arnoldの独自接続も考慮
        shaders = mc.listConnections(f"{sg_nodes[0]}.aiSurfaceShader")
        return shaders[0] if shaders else None
        
    def _is_texture_connected(self, shader, tex_type):
        """指定されたシェーダの特定テクスチャタイプに接続があるか確認する"""
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

    # --------------------------------------------------------------------------
    # UIコントロール用スロット
    # --------------------------------------------------------------------------

    def update_subdiv_text(self, value):
        self.subdiv_line_edit.setText(str(value))

    def update_subdiv_slider(self):
        try:
            value = int(self.subdiv_line_edit.text())
            self.subdiv_slider.setValue(value)
            self.apply_subdivision_iterations()
        except ValueError:
            pass # 不正な入力は無視

    def update_height_text(self, value):
        self.height_line_edit.setText(f"{value / 100.0:.2f}")

    def update_height_slider(self):
        try:
            value = float(self.height_line_edit.text())
            self.height_slider.setValue(int(value * 100))
            self.apply_displacement_height()
        except ValueError:
            pass # 不正な入力は無視

    # --------------------------------------------------------------------------
    # メイン機能 (マテリアル・テクスチャ操作)
    # --------------------------------------------------------------------------

    def apply_subdivision_iterations(self):
        """Subdivision Iterationsの値をオブジェクトに適用する"""
        value = self.subdiv_slider.value()
        shape = self.get_selected_shape()
        if shape and mc.objExists(shape) and mc.attributeQuery('aiSubdivIterations', node=shape, exists=True):
            mc.setAttr(f"{shape}.aiSubdivIterations", value)

    def apply_displacement_height(self):
        """Displacement Heightの値をシェイプノードのaiDispHeightに適用する"""
        value = self.height_slider.value() / 100.0
        shape = self.get_selected_shape()
        if shape and mc.objExists(shape) and mc.attributeQuery('aiDispHeight', node=shape, exists=True):
            mc.setAttr(f"{shape}.aiDispHeight", value)

    def process_selection(self):
        """選択されたオブジェクトに対してマテリアル作成と割り当てを実行する"""
        selection = mc.ls(selection=True, long=True)
        if not selection:
            self.status_label.setText("<font color='red'>エラー: オブジェクトが選択されていません。</font>")
            return

        valid_objects = [s for s in selection if mc.listRelatives(s, shapes=True, type='mesh', fullPath=True)]
        if not valid_objects:
            self.status_label.setText("<font color='orange'>警告: ポリゴンメッシュが選択されていません。</font>")
            return

        self.status_label.setText("処理中...")
        QtWidgets.QApplication.processEvents()

        created_count, assigned_count = 0, 0
        for obj_path in valid_objects:
            obj_name = obj_path.split('|')[-1]
            try:
                is_created = self.create_and_assign_material(obj_path, obj_name)
                if is_created: created_count += 1
                else: assigned_count += 1
            except Exception as e:
                mc.warning(f"{obj_name} のマテリアル処理に失敗: {e}")
        
        self.status_label.setText(f"<font color='green'>成功: {created_count}個のマテリアルを作成, {assigned_count}個を割り当て。</font>")
        self.populate_material_list()
        self.update_selection_info()

    def create_and_assign_material(self, obj_path, obj_name):
        """一つのオブジェクトに対して、マテリアル作成と割り当てを行う"""
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', obj_name)
        shader_name = f"{clean_name}_mat"
        
        # 既存のマテリアルを検索
        if mc.objExists(shader_name) and mc.nodeType(shader_name) == 'aiStandardSurface':
            shader_node = shader_name
            is_new_material = False
        else:
            # 新規作成
            shader_node = mc.shadingNode('aiStandardSurface', asShader=True, name=shader_name)
            is_new_material = True

        # シェーディンググループの取得または作成
        sg_connections = mc.listConnections(shader_node, d=True, s=False, type="shadingEngine")
        if sg_connections:
            sg_node = sg_connections[0]
        else:
            sg_node = mc.sets(renderable=True, noSurfaceShader=True, empty=True, name=f"{shader_node}SG")
            mc.connectAttr(f'{shader_node}.outColor', f'{sg_node}.surfaceShader')
        
        # オブジェクトへの割り当て
        mc.sets(obj_path, edit=True, forceElement=sg_node)
        return is_new_material

    def toggle_texture_connection_by_type(self, tex_type):
        """指定タイプのテクスチャ接続をトグルする"""
        self.status_label.setText(f"'{tex_type}' 接続をトグル中...")
        QtWidgets.QApplication.processEvents()
        
        original_selection = mc.ls(sl=True, long=True)
        shader = self.get_shader_from_selection()
        
        if not shader:
            self.status_label.setText("<font color='orange'>操作対象のマテリアルがありません。</font>")
            return

        if self._is_texture_connected(shader, tex_type):
            self._cleanup_single_connection(shader, tex_type)
        else:
            if original_selection:
                obj_path = original_selection[0]
                material_name = shader # シェーダ名をベースにする
                self._connect_single_texture(shader, material_name, tex_type, obj_path)
            else:
                self.status_label.setText("<font color='orange'>テクスチャ接続にはオブジェクトの選択が必要です。</font>")

        # 処理中に選択が外れることがあるため、再選択する
        if original_selection:
            mc.select(original_selection, replace=True)
            
        mc.evalDeferred(self.update_selection_info)
        self.status_label.setText(f"<font color='blue'>{tex_type} 接続をトグルしました。</font>")

    def _connect_single_texture(self, shader_node, material_name, tex_type, obj_path):
        """指定された単一タイプのテクスチャを検索し、シェーダに接続する"""
        texture_dir = self._get_texture_directory(material_name)
        if not texture_dir:
            mc.warning(f"テクスチャディレクトリが見つかりません: {material_name}")
            self.status_label.setText(f"<font color='red'>ディレクトリが見つかりません: {material_name}</font>")
            return

        texture_path = self.find_texture_file(texture_dir, tex_type)
        if not texture_path:
            mc.warning(f"'{tex_type}' テクスチャが '{texture_dir}' に見つかりません。")
            self.status_label.setText(f"<font color='orange'>'{tex_type}' テクスチャが見つかりません。</font>")
            return

        # 既存の接続をクリーンアップ
        self._cleanup_single_connection(shader_node, tex_type)

        file_node, _ = self._create_texture_file_node(material_name, tex_type, texture_path)
        
        try:
            if tex_type == "normal":
                normal_map_node = mc.shadingNode('aiNormalMap', asUtility=True, name=f"{material_name}_NRM")
                mc.connectAttr(f"{file_node}.outColor", f"{normal_map_node}.input")
                mc.connectAttr(f"{normal_map_node}.outValue", f"{shader_node}.normalCamera")
            elif tex_type == "displacement":
                disp_shader_node = mc.shadingNode('displacementShader', asShader=True, name=f"{material_name}_DISP")
                sg_nodes = mc.listConnections(shader_node, type='shadingEngine')
                if sg_nodes:
                    mc.connectAttr(f"{file_node}.outAlpha", f"{disp_shader_node}.displacement")
                    mc.connectAttr(f"{disp_shader_node}.displacement", f"{sg_nodes[0]}.displacementShader")
                    shapes = mc.listRelatives(obj_path, shapes=True, fullPath=True, type='mesh')
                    if shapes:
                        for shape in shapes:
                            mc.setAttr(f"{shape}.aiSubdivType", 1) # Catclark
            elif tex_type == "base_color":
                mc.connectAttr(f"{file_node}.outColor", f"{shader_node}.{ATTRIBUTE_MAP[tex_type]}", force=True)
            elif tex_type == "opacity":
                mc.connectAttr(f"{file_node}.outColor", f"{shader_node}.{ATTRIBUTE_MAP[tex_type]}", force=True)
            else: # metalness, roughnessなど (Alpha is Luminance)
                mc.connectAttr(f"{file_node}.outAlpha", f"{shader_node}.{ATTRIBUTE_MAP[tex_type]}", force=True)
            
            print(f"接続成功: {texture_path} -> {shader_node}")
        except Exception as e:
            print(f"接続失敗: {file_node} -> {shader_node}: {e}")

    def _cleanup_single_connection(self, shader, tex_type):
        """指定シェーダの特定テクスチャタイプの接続と関連ノードを削除する"""
        full_attr = ""
        if tex_type == "normal":
            full_attr = f"{shader}.normalCamera"
        elif tex_type == "displacement":
            sg_nodes = mc.listConnections(shader, type='shadingEngine')
            if sg_nodes: full_attr = f"{sg_nodes[0]}.displacementShader"
            else: return
        else:
            attr_name = ATTRIBUTE_MAP.get(tex_type)
            if not attr_name: return
            full_attr = f"{shader}.{attr_name}"

        source_node = mc.listConnections(full_attr, s=True, d=False, p=False)
        if source_node:
            # 接続に関連する上流ノード（file, place2d, utilityなど）を取得して削除
            history = mc.listHistory(source_node[0])
            nodes_to_delete = {node for node in history if mc.nodeType(node) in ['file', 'place2dTexture', 'aiNormalMap', 'bump2d', 'displacementShader']}
            if nodes_to_delete:
                mc.delete(list(nodes_to_delete))

    def _create_texture_file_node(self, material_name, tex_type, texture_path):
        """fileノードとplace2dTextureノードを作成し、設定を行う"""
        file_node_name = f"{material_name}_{tex_type}_file"
        p2d_node_name = f"{material_name}_{tex_type}_p2d"

        file_node = mc.shadingNode('file', asTexture=True, name=file_node_name, isColorManaged=True)
        p2d_node = mc.shadingNode('place2dTexture', asUtility=True, name=p2d_node_name)
        
        # place2dTextureをfileノードに接続
        mc.connectAttr(f'{p2d_node}.coverage', f'{file_node}.coverage', f=True)
        mc.connectAttr(f'{p2d_node}.translateFrame', f'{file_node}.translateFrame', f=True)
        mc.connectAttr(f'{p2d_node}.rotateFrame', f'{file_node}.rotateFrame', f=True)
        mc.connectAttr(f'{p2d_node}.mirrorU', f'{file_node}.mirrorU', f=True)
        mc.connectAttr(f'{p2d_node}.mirrorV', f'{file_node}.mirrorV', f=True)
        mc.connectAttr(f'{p2d_node}.stagger', f'{file_node}.stagger', f=True)
        mc.connectAttr(f'{p2d_node}.wrapU', f'{file_node}.wrapU', f=True)
        mc.connectAttr(f'{p2d_node}.wrapV', f'{file_node}.wrapV', f=True)
        mc.connectAttr(f'{p2d_node}.repeatUV', f'{file_node}.repeatUV', f=True)
        mc.connectAttr(f'{p2d_node}.offset', f'{file_node}.offset', f=True)
        mc.connectAttr(f'{p2d_node}.rotateUV', f'{file_node}.rotateUV', f=True)
        mc.connectAttr(f'{p2d_node}.noiseUV', f'{file_node}.noiseUV', f=True)
        mc.connectAttr(f'{p2d_node}.outUV', f'{file_node}.uvCoord', f=True)
        mc.connectAttr(f'{p2d_node}.outUvFilterSize', f'{file_node}.uvFilterSize', f=True)
        
        mc.setAttr(f"{file_node}.fileTextureName", texture_path, type="string")

        if "<UDIM>" in texture_path:
            mc.setAttr(f"{file_node}.uvTilingMode", 3) # UDIM (Mari)

        # カラーマネジメントと設定
        if tex_type in LINEAR_WORKFLOW_TYPES:
            mc.setAttr(f"{file_node}.colorSpace", "Raw", type="string")
            mc.setAttr(f"{file_node}.alphaIsLuminance", True)
        else: # base_color
            mc.setAttr(f"{file_node}.colorSpace", "sRGB", type="string")
            mc.setAttr(f"{file_node}.alphaIsLuminance", False)

        return file_node, p2d_node

    # --------------------------------------------------------------------------
    # テクスチャパス管理
    # --------------------------------------------------------------------------

    def get_texture_root_dir(self):
        """UIから現在のテクスチャ検索ルートパスを取得する"""
        custom_path = self.custom_path_combo.currentText()
        if custom_path and custom_path != "[Default] Project's sourceimages" and os.path.isdir(custom_path):
            return custom_path.replace("\\", "/")
        
        project_path = mc.workspace(q=True, rd=True)
        source_images_folder = mc.workspace(fileRuleEntry='sourceImages')
        return os.path.join(project_path, source_images_folder).replace("\\", "/")
        
    def update_active_path_display(self):
        """現在有効なテクスチャ検索パスをUIに表示する"""
        active_path = self.get_texture_root_dir()
        self.active_path_label.setText(f"アクティブパス: {active_path}")

    def _get_texture_directory(self, material_name):
        """指定されたマテリアル名に対応するテクスチャフォルダのパスを返す"""
        root_dir = self.get_texture_root_dir()
        # まずはマテリアル名と完全に一致するフォルダを探す
        specific_texture_dir = os.path.join(root_dir, material_name)
        if os.path.isdir(specific_texture_dir):
            return specific_texture_dir
        
        # 見つからない場合、末尾の "_mat" などを削除して探す
        base_name = material_name.rsplit('_', 1)[0]
        base_texture_dir = os.path.join(root_dir, base_name)
        if os.path.isdir(base_texture_dir):
            return base_texture_dir
            
        # それでも見つからない場合はルートを返す
        return root_dir

    def find_texture_file(self, texture_dir, texture_type):
        """指定フォルダ内から特定のテクスチャタイプのファイルを探す"""
        if not os.path.isdir(texture_dir): return None
        
        udim_pattern = re.compile(r'(.+?)[._](\d{4})\.(.+)$', re.IGNORECASE)
        
        try: filenames = os.listdir(texture_dir)
        except OSError: return None

        # UDIMファイルの検索
        udim_sets = {}
        for filename in filenames:
            if texture_type.lower() in filename.lower():
                match = udim_pattern.match(filename)
                if match:
                    base_name, _, ext = match.groups()
                    udim_path = os.path.join(texture_dir, f"{base_name}.<UDIM>.{ext}").replace("\\", "/")
                    return udim_path

        # 単一ファイルの検索
        for filename in filenames:
            if texture_type.lower() in filename.lower():
                 return os.path.join(texture_dir, filename).replace("\\", "/")
                 
        return None

    def browse_for_path(self):
        """フォルダ選択ダイアログを開き、パスを設定する"""
        result = mc.fileDialog2(fileMode=3, dialogStyle=2, startingDirectory=self.get_texture_root_dir())
        if result:
            self.custom_path_combo.setCurrentText(result[0])
            self.add_current_path_to_history()

    def add_current_path_to_history(self):
        """現在のパスをMayaのoptionVarに保存する"""
        path_to_save = self.custom_path_combo.currentText()
        if not (path_to_save and os.path.isdir(path_to_save)):
            return
        
        saved_paths_str = mc.optionVar(q=OPTION_VAR_KEY) if mc.optionVar(exists=OPTION_VAR_KEY) else ""
        saved_paths = saved_paths_str.split(';') if saved_paths_str else []
        
        if path_to_save in saved_paths:
            saved_paths.remove(path_to_save)
        saved_paths.insert(0, path_to_save) # 先頭に追加
        
        mc.optionVar(stringValue=(OPTION_VAR_KEY, ';'.join(saved_paths[:20]))) # 履歴は20件まで
        self.load_saved_paths()
        self.custom_path_combo.setCurrentText(path_to_save)
        self.status_label.setText("<font color='blue'>パスの履歴を更新しました。</font>")

    def load_saved_paths(self):
        """保存されたパスをoptionVarから読み込む"""
        self.custom_path_combo.blockSignals(True)
        current_text = self.custom_path_combo.currentText()
        self.custom_path_combo.clear()
        
        self.custom_path_combo.addItem("[Default] Project's sourceimages")

        if mc.optionVar(exists=OPTION_VAR_KEY):
            saved_paths = mc.optionVar(q=OPTION_VAR_KEY).split(';')
            self.custom_path_combo.addItems([p for p in saved_paths if p])
        
        index = self.custom_path_combo.findText(current_text)
        if index != -1: self.custom_path_combo.setCurrentIndex(index)
        else: self.custom_path_combo.setCurrentIndex(0)

        self.custom_path_combo.blockSignals(False)
        self.update_active_path_display()
        
    # --------------------------------------------------------------------------
    # ユーティリティ機能
    # --------------------------------------------------------------------------
    
    # ★★★ 変更点: 新しいメソッドを追加 ★★★
    def set_default_subdivision(self):
        """
        選択されたメッシュのArnoldサブディビジョン設定を有効にし、
        イテレーションを2に、タイプを'catclark'に設定します。
        """
        selected_objects = mc.ls(selection=True, long=True)
        if not selected_objects:
            self.status_label.setText("<font color='orange'>オブジェクトが選択されていません。</font>")
            mc.warning("No objects selected.")
            return

        meshes_found = False
        processed_count = 0
        for obj in selected_objects:
            # トランスフォームノードからシェイプノードを取得
            shapes = mc.listRelatives(obj, shapes=True, fullPath=True, type='mesh')
            if not shapes:
                continue

            for shape in shapes:
                meshes_found = True
                print(f"Applying subdivision settings to: {shape}")
                
                try:
                    # aiSubdivType アトリビュートを設定 (1は 'catclark')
                    if mc.attributeQuery('aiSubdivType', node=shape, exists=True):
                        mc.setAttr(f"{shape}.aiSubdivType", 1)
                    else:
                        mc.warning(f"{shape} に 'aiSubdivType' アトリビュートがありません。")

                    # aiSubdivIterations アトリビュートを設定
                    if mc.attributeQuery('aiSubdivIterations', node=shape, exists=True):
                        mc.setAttr(f"{shape}.aiSubdivIterations", 2)
                    else:
                        mc.warning(f"{shape} に 'aiSubdivIterations' アトリビュートがありません。")
                    processed_count += 1
                except Exception as e:
                    mc.warning(f"Failed to set subdivision for {shape}: {e}")

        if not meshes_found:
            self.status_label.setText("<font color='orange'>選択内にメッシュが見つかりません。</font>")
            mc.warning("No mesh shapes found in the selection.")
        else:
            self.status_label.setText(f"<font color='green'>{processed_count}個のメッシュにSubdivisionを設定しました。</font>")
            # UIを更新してスライダーに反映
            self.update_arnold_attributes_ui()
            
    def toggle_all_normal_invert_y(self):
        """シーン内の全てのaiNormalMapノードのInvert Yアトリビュートをトグルする"""
        normal_nodes = mc.ls(type='aiNormalMap')
        if not normal_nodes:
            self.status_label.setText("<font color='orange'>シーンにaiNormalMapノードがありません。</font>")
            return
        
        toggled_count = 0
        for node in normal_nodes:
            try:
                current_value = mc.getAttr(f"{node}.invertY")
                mc.setAttr(f"{node}.invertY", not current_value)
                toggled_count += 1
            except Exception as e:
                mc.warning(f"{node}のInvert Yのトグルに失敗しました: {e}")
                
        self.status_label.setText(f"<font color='green'>{toggled_count}個のaiNormalMapノードのInvert Yをトグルしました。</font>")

    def reload_all_textures(self):
        """シーン内の全てのfileノードのテクスチャをリロードする"""
        file_nodes = mc.ls(type='file')
        if not file_nodes:
            self.status_label.setText("<font color='orange'>シーンにfileノードがありません。</font>")
            return
            
        reloaded_count = 0
        for node in file_nodes:
            try:
                # Mayaの内部リロードコマンドを使用するのが最も確実
                mel.eval(f'AEfileTextureReloadCmd "{node}"')
                reloaded_count += 1
            except Exception as e:
                mc.warning(f"テクスチャのリロードに失敗しました {node}: {e}")
                
        self.status_label.setText(f"<font color='green'>{reloaded_count}個のテクスチャをリロードしました。</font>")
        print(f"Reloaded {reloaded_count} textures.")

    def delete_unused_nodes(self):
        """未使用のシェーディングノードを削除する"""
        try:
            mel.eval('hyperShadePanelMenuCommand("hyperShadePanel1", "deleteUnusedNodes");')
            self.status_label.setText("<font color='green'>未使用ノードを削除しました。</font>")
            print("Deleted unused nodes.")
            self.populate_material_list() # マテリアルリストを更新
        except Exception as e:
            self.status_label.setText("<font color='red'>未使用ノードの削除に失敗しました。</font>")
            mc.warning(f"Failed to delete unused nodes: {e}")

# --- ウィンドウの起動と管理 ---
material_manager_window_instance = None

def show_material_manager_window():
    """
    ウィンドウを起動するための関数。
    既存のウィンドウがあれば、それを閉じてから新しく開く。
    """
    global material_manager_window_instance
    if material_manager_window_instance is not None:
        try:
            material_manager_window_instance.close()
            material_manager_window_instance.deleteLater()
        except Exception as e:
            print(f"既存ウィンドウのクローズ中にエラーが発生: {e}")
    
    # Mayaのメインウィンドウを親としてウィンドウをインスタンス化
    maya_main_window = get_maya_main_window()
    material_manager_window_instance = MaterialTextureManagerWindow(parent=maya_main_window)
    material_manager_window_instance.show()
    return material_manager_window_instance

# --- スクリプトの実行 ---
if __name__ == "__main__":
    # Mayaのスクリプトエディタで実行した際にウィンドウを表示
    show_material_manager_window()

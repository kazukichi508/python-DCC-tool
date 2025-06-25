import hou
import os
from PySide2 import QtWidgets, QtCore, QtGui

class FbxImporterWindow(QtWidgets.QWidget):


    def __init__(self):
        super(FbxImporterWindow, self).__init__()
        self.setWindowTitle("FBX/Alembic Importer for Houdini 20.5")
        self.setGeometry(100, 100, 500, 180) # ウィンドウの高さを元に戻す

        self.initUI()

    def initUI(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        path_layout = QtWidgets.QHBoxLayout()
        self.path_label = QtWidgets.QLabel("FBX/Alembic Directory:")
        path_layout.addWidget(self.path_label)

        self.path_lineEdit = QtWidgets.QLineEdit()
        initial_geo_cache_dir = hou.text.expandString('$JOB/geo_cache')
        normalized_initial_path = os.path.normpath(initial_geo_cache_dir).replace('\\', '/')
        self.path_lineEdit.setText(normalized_initial_path)
        path_layout.addWidget(self.path_lineEdit)

        self.browse_button = QtWidgets.QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_fbx_directory)
        path_layout.addWidget(self.browse_button)
        main_layout.addLayout(path_layout)

        button_layout = QtWidgets.QHBoxLayout()
        
        self.import_button = QtWidgets.QPushButton("Stageにインポート")
        self.import_button.clicked.connect(self.run_import_process)
        button_layout.addWidget(self.import_button)

        self.reload_button = QtWidgets.QPushButton("リロード")
        self.reload_button.setToolTip("Deletes all previously imported nodes and re-imports from the specified directory.")
        self.reload_button.clicked.connect(self.run_import_process)
        button_layout.addWidget(self.reload_button)
        
        main_layout.addLayout(button_layout)

        arrange_layout = QtWidgets.QHBoxLayout()
        self.arrange_nodes_button = QtWidgets.QPushButton("ノードを整理")
        self.arrange_nodes_button.setToolTip("Automatically arranges nodes in /obj and /stage.")
        self.arrange_nodes_button.clicked.connect(self.arrange_all_nodes)
        arrange_layout.addWidget(self.arrange_nodes_button)
        main_layout.addLayout(arrange_layout)

        self.status_label = QtWidgets.QLabel("Ready.")
        main_layout.addWidget(self.status_label)
        
        self.setLayout(main_layout)

    def browse_fbx_directory(self):
        current_path = self.path_lineEdit.text()
        if not os.path.isdir(current_path):
            current_path = hou.text.expandString('$HIP')
            if not os.path.isdir(current_path):
                current_path = os.path.expanduser("~")

        selected_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select FBX/Alembic Directory", current_path,
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )

        if selected_dir:
            normalized_selected_dir = os.path.normpath(selected_dir).replace('\\', '/')
            self.path_lineEdit.setText(normalized_selected_dir)
            self.status_label.setText("Directory selected.")

    def cleanup_existing_nodes(self):
        self.status_label.setText("Cleaning up existing nodes...")
        QtWidgets.QApplication.processEvents()
        
        obj_node = hou.node('/obj')
        stage_node = hou.node('/stage')

        dir_path = self.path_lineEdit.text()
        potential_names_to_delete = []
        if os.path.isdir(dir_path):
            for f in os.listdir(dir_path):
                if f.lower().endswith(('.fbx', '.abc')):
                    base_name_without_ext = os.path.basename(f).rsplit('.', 1)[0]
                    sanitized_name = ''.join(c if c.isalnum() else '_' for c in base_name_without_ext)
                    potential_names_to_delete.append(sanitized_name)

        if obj_node and potential_names_to_delete:
            for node in obj_node.children():
                # ノード名がサニタイズされたファイル名と一致するかどうかで判断
                if node.type().name() == 'geo' and node.name() in potential_names_to_delete:
                    print(f"Deleting existing geo node: {node.path()}")
                    node.destroy()

        if stage_node and potential_names_to_delete:
            for node in stage_node.children():
                if node.type().name() == 'sopimport' and node.name() in potential_names_to_delete:
                    print(f"Deleting existing sopimport node: {node.path()}")
                    node.destroy()
        
        print("Cleanup complete.")


    def arrange_all_nodes(self):
        QtWidgets.QApplication.processEvents()

        obj_node = hou.node('/obj')
        if obj_node:
            print("Arranging nodes in /obj...")
            obj_node.layoutChildren()

        stage_node = hou.node('/stage')
        if stage_node:
            print("Arranging nodes in /stage...")
            stage_node.layoutChildren()
        
        self.status_label.setText("Nodes arranged.")
        print("Node arrangement complete.")

    def run_import_process(self):
        self.cleanup_existing_nodes()
        self.execute_import()
        self.arrange_all_nodes()

    def execute_import(self):
        dir_path = self.path_lineEdit.text()
        
        if not os.path.isdir(dir_path):
            self.status_label.setText(f"<font color='red'>エラー: '{dir_path}' は有効なディレクトリではありません。</font>")
            return

        self.status_label.setText("Importing FBX/Alembic files... Please wait.")
        QtWidgets.QApplication.processEvents()

        try:
            target_files = []
            for f in os.listdir(dir_path):
                if f.lower().endswith(('.fbx', '.abc')):
                    target_files.append(os.path.normpath(os.path.join(dir_path, f)).replace('\\', '/'))
            
            if not target_files:
                self.status_label.setText(f"<font color='orange'>警告: '{dir_path}' にFBXまたはAlembicファイルが見つかりませんでした。</font>")
                return

            obj_node = hou.node('/obj')
            if not obj_node:
                self.status_label.setText("<font color='red'>重大なエラー: '/obj' が見つかりません。</font>")
                return

            created_geo_nodes = []
            for i, target_file_path in enumerate(target_files):
                base_name_without_ext = os.path.basename(target_file_path).rsplit('.', 1)[0]
                sanitized_name = ''.join(c if c.isalnum() else '_' for c in base_name_without_ext)
                
                geo_node_name = sanitized_name
                
                try:
                    geo_node = obj_node.createNode('geo', geo_node_name)
                    print(f"Created geo node: {geo_node.path()}")
                    
                    file_node = geo_node.createNode('file', 'file_import')
                    file_node.parm('file').set(target_file_path)
                    
                    file_node.setDisplayFlag(True)
                    file_node.setRenderFlag(True)
                    
                    created_geo_nodes.append(geo_node)

                except hou.OperationFailed as e:
                    error_msg = f"エラー: geo/fileノード作成中に失敗: {e}"
                    self.status_label.setText(f"<font color='red'>{error_msg}</font>")
                    print(error_msg)
                    continue

            if not created_geo_nodes:
                self.status_label.setText("<font color='orange'>警告: geoノードが一つも作成されませんでした。</font>")
                return

            stage_node = hou.node('/stage')
            if not stage_node:
                print("'/stage' not found. Creating a new LOP Network named 'stage'.")
                self.status_label.setText("'/stage' が見つからないため、新規作成します...")
                QtWidgets.QApplication.processEvents()
                stage_node = obj_node.createNode('lopnet', 'stage') 
                if not stage_node:
                    self.status_label.setText("<font color='red'>重大なエラー: '/stage' の作成に失敗しました。</font>")
                    return
            
            stage_content_node = stage_node
            
            print("\n--- Starting import to Stage ---")
            last_sop_import = None
            for i, geo_node in enumerate(created_geo_nodes):
                sop_import_name = geo_node.name() 
                
                try:
                    sop_import_node = stage_content_node.createNode('sopimport', sop_import_name)
                    print(f"Created SOP Import node: {sop_import_node.path()}")
                    
                    sop_import_node.parm('soppath').set(geo_node.path())
                    print(f"   Set 'SOP Path' to: {geo_node.path()}")
                    
                    sop_import_node.parm('copycontents').set(True)
                    print("   Set 'copycontents' to True.")
                    
                    if last_sop_import:
                        sop_import_node.setInput(0, last_sop_import)
                    
                    last_sop_import = sop_import_node

                except hou.OperationFailed as e:
                    error_msg = f"エラー: SOP Importノード作成中に失敗: {e}"
                    self.status_label.setText(f"<font color='red'>{error_msg}</font>")
                    print(error_msg)
            
            if last_sop_import:
                last_sop_import.setDisplayFlag(True)
                last_sop_import.setRenderFlag(True)

            self.status_label.setText("<font color='green'>FBX/AlembicファイルのインポートとStageへの取り込みが完了しました！</font>")

        except Exception as e:
            self.status_label.setText(f"<font color='red'>予期せぬスクリプトエラーが発生しました: {e}</font>")
            print(f"Python Error: {e}")

def show_fbx_importer_window():
    global fbx_importer_window
    # 既存のウィンドウを安全に閉じる
    for widget in QtWidgets.QApplication.allWidgets():
        if isinstance(widget, FbxImporterWindow):
            widget.close()
            widget.deleteLater()

    parent = hou.ui.mainQtWindow()
    fbx_importer_window = FbxImporterWindow()
    fbx_importer_window.setParent(parent, QtCore.Qt.Window) 
    fbx_importer_window.show()

show_fbx_importer_window()

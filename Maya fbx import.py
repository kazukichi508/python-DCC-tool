import maya.cmds as cmds
from PySide6 import QtWidgets, QtCore, QtGui
import os

from maya.app.general.mayaMixin import MayaQWidgetBaseMixin

FILE_LOADER_WINDOW = None
class FileLoaderWindow(MayaQWidgetBaseMixin, QtWidgets.QDialog):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("インポート ツール")
        self.setMinimumWidth(550)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.selected_file_path = ""
        self.create_widgets()
        self.create_layout()
        self.create_connections()

    def create_widgets(self):
        self.file_path_label = QtWidgets.QLineEdit("ファイルを選択")
        self.file_path_label.setReadOnly(True)
        self.browse_button = QtWidgets.QPushButton("ファイル参照...")
        self.import_file_button = QtWidgets.QPushButton("選択ファイルをインポート")
        self.import_file_button.setEnabled(False)

        self.name_filter_line_edit = QtWidgets.QLineEdit()
        self.name_filter_line_edit.setPlaceholderText("例: character, prop_ (空の場合は全て対象)")

        self.import_folder_button = QtWidgets.QPushButton("フォルダからインポート")

    def create_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        file_layout = QtWidgets.QHBoxLayout()
        file_layout.addWidget(QtWidgets.QLabel("個別ファイル:"))
        file_layout.addWidget(self.file_path_label)
        file_layout.addWidget(self.browse_button)

        name_filter_layout = QtWidgets.QHBoxLayout()
        name_filter_layout.addWidget(QtWidgets.QLabel("名前フィルター:"))
        name_filter_layout.addWidget(self.name_filter_line_edit)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.import_folder_button)
        button_layout.addWidget(self.import_file_button)

        main_layout.addLayout(file_layout)
        main_layout.addSpacing(5)
        main_layout.addLayout(name_filter_layout)
        main_layout.addSpacing(10)
        main_layout.addLayout(button_layout)

    def create_connections(self):
        self.browse_button.clicked.connect(self.browse_file_slot)
        self.import_file_button.clicked.connect(self.import_file_slot)
        self.import_folder_button.clicked.connect(self.import_from_folder_slot)

    def perform_import(self, file_path):
        try:
            print(f"インポート中: {file_path}")
            file_type = self.get_file_type(file_path)
            if file_type == 'FBX':
                self.ensure_plugin_loaded('fbxmaya')
            elif file_type == 'OBJ':
                self.ensure_plugin_loaded('objExport')

            cmds.file(
                file_path, i=True, type=file_type, ignoreVersion=True,
                mergeNamespacesOnClash=False, options="v=0;"
            )
            return True
        except Exception as e:
            print(f"エラー: ファイル '{os.path.basename(file_path)}' のインポートに失敗しました。詳細: {e}")
            cmds.warning(f"インポート失敗: {os.path.basename(file_path)}")
            return False


    def import_from_folder_slot(self):
        result = cmds.fileDialog2(fileMode=3, caption="インポートしたいファイルが含まれるフォルダを選択")
        if not result:
            print("フォルダ選択がキャンセルされました。")
            return

        folder_path = result[0]
        name_filter = self.name_filter_line_edit.text()

        print(f"--- フォルダからの一括インポート開始: {folder_path} ---")
        if name_filter:
            print(f"--- 名前フィルター: '{name_filter}' ---")

        target_extensions = ('.ma', '.mb', '.fbx', '.obj')
        files_to_import = []

        for filename in sorted(os.listdir(folder_path)):
            is_target_ext = filename.lower().endswith(target_extensions)
            is_name_match = not name_filter or name_filter in filename

            if is_target_ext and is_name_match:
                full_path = os.path.join(folder_path, filename)
                files_to_import.append(full_path)

        if not files_to_import:
            if name_filter:
                msg = f"フォルダ '{os.path.basename(folder_path)}' 内に、名前に '{name_filter}' を含む対象ファイルが見つかりませんでした。"
            else:
                msg = f"フォルダ '{os.path.basename(folder_path)}' 内に対象ファイルが見つかりませんでした。"
            cmds.warning(msg)
            print(msg)
            return

        imported_count = 0
        total_count = len(files_to_import)
        for i, file_path in enumerate(files_to_import):
            print(f"[{i+1}/{total_count}] を処理中...")
            if self.perform_import(file_path):
                imported_count += 1
        
        failed_count = total_count - imported_count
        final_message = f"一括インポート完了。\n成功: {imported_count}件, 失敗: {failed_count}件"
        print(final_message)
        cmds.inViewMessage(assistMessage=final_message, position='midCenter', fade=True, fadeOutTime=2000)

    def import_file_slot(self):
        if not self.selected_file_path or not os.path.exists(self.selected_file_path):
            cmds.warning("有効なファイルパスが指定されていません。")
            return
        if self.perform_import(self.selected_file_path):
            cmds.inViewMessage(
                assistMessage=f"ファイルをインポートしました:\n{os.path.basename(self.selected_file_path)}",
                position='midCenter', fade=True
            )

    def browse_file_slot(self):
        file_filter = "3D Files (*.ma *.mb *.fbx *.obj);;All (*.*)"
        result = cmds.fileDialog2(fileMode=1, caption="インポートするファイルを選択", fileFilter=file_filter)
        if result:
            self.selected_file_path = result[0]
            self.file_path_label.setText(self.selected_file_path)
            self.import_file_button.setEnabled(True)
        else:
            self.file_path_label.setText("ファイル選択がキャンセルされました。")
            self.import_file_button.setEnabled(False)

    def ensure_plugin_loaded(self, plugin_name):
        if not cmds.pluginInfo(plugin_name, query=True, loaded=True):
            cmds.loadPlugin(plugin_name, quiet=True)

    def get_file_type(self, file_path):
        extension = os.path.splitext(file_path)[1].lower()
        type_map = {'.ma': 'mayaAscii', '.mb': 'mayaBinary', '.fbx': 'FBX', '.obj': 'OBJ'}
        return type_map.get(extension, 'bestGuess')

def show_file_loader_window():
    global FILE_LOADER_WINDOW
    if FILE_LOADER_WINDOW:
        FILE_LOADER_WINDOW.close()
    FILE_LOADER_WINDOW = FileLoaderWindow()
    FILE_LOADER_WINDOW.show()

show_file_loader_window()

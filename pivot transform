import maya.cmds as cmds
import maya.mel as mel

def move_pivot_ui():
    window_name = "pivotMoverWindow"
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name, window=True)

    cmds.window(window_name, title="Pivot Mover", widthHeight=(350, 400))
    cmds.columnLayout(adjustableColumn=True)

    cmds.text(label="選択オブジェクトのピボットを操作します")
    cmds.separator(height=10, style='none')

    cmds.frameLayout(label="ピボット移動 (指定位置)", collapsable=True, collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    cmds.floatFieldGrp("pivotX", numberOfFields=1, label="X:", value1=0.0)
    cmds.floatFieldGrp("pivotY", numberOfFields=1, label="Y:", value1=0.0)
    cmds.floatFieldGrp("pivotZ", numberOfFields=1, label="Z:", value1=0.0)
    cmds.button(label="指定位置に移動 (ワールド座標)", command=move_pivot_to_specified_position)
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(height=10, style='none')

    cmds.frameLayout(label="ピボット移動 (オブジェクトの端)", collapsable=True, collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    cmds.button(label="一番上 (Y+) に移動", command=lambda *args: move_pivot_to_bound_edge("top"))
    cmds.button(label="一番下 (Y-) に移動", command=lambda *args: move_pivot_to_bound_edge("bottom"))
    cmds.button(label="一番左 (X-) に移動", command=lambda *args: move_pivot_to_bound_edge("left"))
    cmds.button(label="一番右 (X+) に移動", command=lambda *args: move_pivot_to_bound_edge("right"))
    cmds.button(label="一番奥 (Z-) に移動", command=lambda *args: move_pivot_to_bound_edge("back"))
    cmds.button(label="一番手前 (Z+) に移動", command=lambda *args: move_pivot_to_bound_edge("front"))
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(height=10, style='none')

    cmds.frameLayout(label="ピボットリセット", collapsable=True, collapse=False)
    cmds.columnLayout(adjustableColumn=True)
    cmds.button(label="オブジェクトの中心にリセット", command=reset_pivot_to_center)
    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(height=10, style='none')

    cmds.button(label="閉じる", command=lambda *args: cmds.deleteUI(window_name, window=True))

    cmds.showWindow(window_name)

def move_pivot_to_specified_position(*args):
    selected_objects = cmds.ls(selection=True)
    if not selected_objects:
        cmds.warning("オブジェクトを選択してください。")
        return

    x = cmds.floatFieldGrp("pivotX", query=True, value1=True)
    y = cmds.floatFieldGrp("pivotY", query=True, value1=True)
    z = cmds.floatFieldGrp("pivotZ", query=True, value1=True)

    for obj in selected_objects:
        cmds.xform(obj, pivots=[x, y, z], worldSpace=True)
        print(f"'{obj}' のピボットを ({x:.3f}, {y:.3f}, {z:.3f}) に移動しました。")

def move_pivot_to_bound_edge(edge_type):
    selected_objects = cmds.ls(selection=True)
    if not selected_objects:
        cmds.warning("オブジェクトを選択してください。")
        return

    for obj in selected_objects:
        # オブジェクトのワールド空間でのバウンディングボックスを取得
        # bboxは [minX, minY, minZ, maxX, maxY, maxZ] のリスト
        bbox = cmds.xform(obj, query=True, boundingBox=True, worldSpace=True)
        min_x, min_y, min_z, max_x, max_y, max_z = bbox

        current_pivot = cmds.xform(obj, query=True, pivots=True, worldSpace=True) # これは常に3つの要素のリスト

        new_pivot_x = current_pivot[0]
        new_pivot_y = current_pivot[1]
        new_pivot_z = current_pivot[2]

        if edge_type == "top":
            new_pivot_y = max_y
        elif edge_type == "bottom":
            new_pivot_y = min_y
        elif edge_type == "left":
            new_pivot_x = min_x
        elif edge_type == "right":
            new_pivot_x = max_x
        elif edge_type == "front":
            new_pivot_z = max_z
        elif edge_type == "back":
            new_pivot_z = min_z


        cmds.xform(obj, pivots=[new_pivot_x, new_pivot_y, new_pivot_z], worldSpace=True)
        print(f"'{obj}' のピボットを '{edge_type}' に移動しました。")

def reset_pivot_to_center(*args):
    selected_objects = cmds.ls(selection=True)
    if not selected_objects:
        cmds.warning("オブジェクトを選択してください。")
        return

    for obj in selected_objects:
        cmds.xform(obj, centerPivots=True)
        print(f"'{obj}' のピボットをオブジェクトの中心にリセットしました。")

move_pivot_ui()

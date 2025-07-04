import maya.cmds as mc
import maya.mel as mm
import functools 


UI_WINDOW_NAME = "cameraSwitcherButtonListWindow"
UI_MAIN_LAYOUT = "cameraListColumnLayout" 

def createCameraSwitcherButtonListUI():
    
    if mc.window(UI_WINDOW_NAME, exists=True):
        mc.deleteUI(UI_WINDOW_NAME, window=True)

    mc.window(UI_WINDOW_NAME, title="Camera Switcher (List)", widthHeight=(250, 100))
    
    mc.scrollLayout() 

    
    mc.columnLayout(adjustableColumn=True, rowSpacing=5, cal='center', parent=UI_WINDOW_NAME)


    mc.button(label="Reload Cameras", command=reloadCameraListUI)
    mc.separator(height=10, style='in') 

   
    mc.columnLayout(UI_MAIN_LAYOUT, adjustableColumn=True, rowSpacing=5, cal='center')
    
    loadCameraButtons()

    mc.setParent("..") 
    mc.setParent("..") 

    mc.showWindow(UI_WINDOW_NAME)

def loadCameraButtons():
   
    if mc.columnLayout(UI_MAIN_LAYOUT, exists=True):
        children = mc.columnLayout(UI_MAIN_LAYOUT, query=True, childArray=True)
        if children:
            mc.deleteUI(children)
        mc.setParent(UI_MAIN_LAYOUT)

    cameras = mc.ls(type='camera', l=True)
    cameraNames = []
    for camShape in cameras:
        transformNode = mc.listRelatives(camShape, parent=True, type='transform', f=True)
        if transformNode:
            cameraNames.append(transformNode[0])

    if not cameraNames:
        mc.text(label="No cameras found in the scene.", parent=UI_MAIN_LAYOUT)
    else:
       
        for cam in cameraNames:
            shortName = cam.split('|')[-1]
            mc.button(label=shortName, command=functools.partial(switchCamera, cam), parent=UI_MAIN_LAYOUT)

   
def reloadCameraListUI(*args):
    if mc.columnLayout(UI_MAIN_LAYOUT, exists=True):
        loadCameraButtons()
        mc.warning("Camera list reloaded.")
    else:
       
        mc.warning("Camera list layout not found, rebuilding entire UI.")
        createCameraSwitcherButtonListUI()

def switchCamera(cameraName, *args):
    currentPanel = mc.getPanel(withFocus=True)
    
    if not currentPanel or not mc.modelPanel(currentPanel, exists=True):
        allModelPanels = mc.getPanel(type='modelPanel')
        if allModelPanels:
            currentPanel = allModelPanels[0]
        else:
            mc.warning("No model panels found in the scene to switch camera.")
            return

    try:
        mc.lookThru(currentPanel, cameraName)
        mc.warning(f"Switched camera in {currentPanel} to: {cameraName}")
    except RuntimeError as e:
        mc.warning(f"Failed to switch camera in {currentPanel} to {cameraName}: {e}")


createCameraSwitcherButtonListUI()

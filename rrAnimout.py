import maya.cmds as cmds
import os
import subprocess
import time
import json
import shutil
import re
import sys
import imp
from functools import partial
import sys, contextlib, os

@contextlib.contextmanager
def suppress_stdout_stderr():
    """마야 USD 익스포트 등에서 콘솔 로그를 잠재움"""
    null = open(os.devnull, 'w')
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = null, null
    try:
        yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        null.close()




# 스크립트 작업 ID를 저장할 전역 변수
scriptJobId = None
projects = {
    "THE_TRAP": "T:/",
    "BTS": "B:/",
    "ARBO_BION": "A:/",
    "CKR": "K:/",
    "DSC": "S:/",
    "FUZZ": "Z:/",
    "COC": "S:/PROJECT/COC/02_Production"
}

ppPath = 'M:/RND/SFtools/2023/pipeline/'

import maya.cmds as cmds

import json, os

# 🔥 애님아웃 전용으로 경로 분리
BROWSER_STATE_PATH = os.path.expanduser("~/_json/animOut_state_maya.json")

def save_browser_state(project, scene, cut, process, file_name):
    """
    씬 브라우저 상태를 JSON으로 저장 (애님아웃은 제외)
    """
    os.makedirs(os.path.dirname(BROWSER_STATE_PATH), exist_ok=True)

    state = {
        "project": project,
        "scene": scene,
        "cut": cut,
        "process": process,
        "file": file_name
    }

    try:
        with open(BROWSER_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        # print(f"[AnimOut] 상태 저장 완료 → {BROWSER_STATE_PATH}")
    except Exception as e:
        cmds.warning(f"[AnimOut] 상태 저장 실패: {e}")

def load_browser_state():
    """
    저장된 씬 브라우저 상태 로드
    """
    if not os.path.exists(BROWSER_STATE_PATH):
        return None
    try:
        with open(BROWSER_STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)

        # 필수 키 확인
        required_keys = {"project", "scene", "cut", "process", "file"}
        if not required_keys.issubset(state.keys()):
            cmds.warning("[AnimOut] 저장된 데이터가 씬 브라우저 포맷과 맞지 않습니다.")
            return None

        return state
    except Exception as e:
        # cmds.warning(f"[AnimOut] 상태 복원 실패: {e}")
        return None



# ---------------------------
# Evaluation Mode Guard
# ---------------------------
class EvalModeGuard:
    """
    컨텍스트 매니저: 임시로 Evaluation Mode를 바꾸고 종료 시 원래 모드로 복구
    temp_mode: 'off'(DG), 'serial', 'parallel'
    """
    def __init__(self, temp_mode='off'):
        self.temp_mode = temp_mode
        self.prev_mode = None

    def __enter__(self):
        try:
            prev = cmds.evaluationManager(q=True, mode=True)
            if isinstance(prev, (list, tuple)):
                prev = prev[0]
            self.prev_mode = prev
            if prev != self.temp_mode:
                cmds.evaluationManager(mode=self.temp_mode)
        except Exception as e:
            cmds.warning(f"[EvalModeGuard] 모드 전환 실패: {e}")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.prev_mode:
                cmds.evaluationManager(mode=self.prev_mode)
        except Exception as e:
            cmds.warning(f"[EvalModeGuard] 원래 모드 복구 실패: {e}")


def remove_malicious_nodes():
    malicious_keywords = ['fuckVirus', 'bleed_gene', 'vaccine', 'leukocyte']
    removed_nodes = []

    for node in cmds.ls(type='script'):
        try:
            content = cmds.getAttr(node + '.before')
            if any(word in content for word in malicious_keywords):
                cmds.lockNode(node, lock=False)
                cmds.delete(node)
                removed_nodes.append(node)
        except:
            continue

    for expr in cmds.ls(type='expression'):
        try:
            content = cmds.getAttr(expr + '.expression')
            if any(word in content for word in malicious_keywords):
                cmds.delete(expr)
                removed_nodes.append(expr)
        except:
            continue

    try:
        all_jobs = cmds.scriptJob(listJobs=True)
        for job in all_jobs:
            if any(word in job for word in malicious_keywords):
                try:
                    job_id = int(job.split(":")[0])
                    cmds.scriptJob(kill=job_id, force=True)
                except:
                    continue
    except:
        pass

    try:
        if cmds.optionVar(exists="deferredEvalString"):
            eval_content = cmds.optionVar(q="deferredEvalString")
            if any(word in eval_content for word in malicious_keywords):
                cmds.optionVar(remove="deferredEvalString")
                removed_nodes.append("evalDeferredString")
    except:
        pass

    try:
        unknown_plugins = cmds.unknownPlugin(q=True, list=True) or []
        for plugin in unknown_plugins:
            try:
                cmds.unknownPlugin(plugin, remove=True)
                removed_nodes.append(f"unknownPlugin:{plugin}")
            except:
                continue
    except:
        pass

    unwanted_plugins = ['Turtle', 'Mayatomr', 'stereoCamera']
    for plugin in unwanted_plugins:
        try:
            if cmds.pluginInfo(plugin, q=True, exists=True):
                if cmds.pluginInfo(plugin, q=True, loaded=True):
                    try:
                        cmds.unloadPlugin(plugin, force=True)
                        removed_nodes.append(f"unload:{plugin}")
                    except:
                        continue
                if cmds.pluginInfo(plugin, q=True, autoload=True):
                    try:
                        cmds.pluginInfo(plugin, e=True, autoload=False)
                        removed_nodes.append(f"noAutoload:{plugin}")
                    except:
                        continue
        except:
            continue

    if removed_nodes:
        print("🧼 다음 항목이 제거됨 또는 비활성화됨:")
        for item in removed_nodes:
            print(" -", item)



def aniPublish():
    sys.path.append(ppPath)
    import sfAniPublish
    imp.reload (sfAniPublish)
    sfAniPublish.publishAni()
    sfAniPublish.backupAni()

def get_current_project():
    """현재 열려있는 파일의 경로를 기반으로 프로젝트를 결정합니다."""
    file_path = cmds.file(query=True, sceneName=True)
    normalized = os.path.normcase(os.path.normpath(file_path or ""))
    if "project\\coc\\02_production" in normalized:
        return 'COC'
    drive = os.path.splitdrive(file_path)[0].upper()  # 드라이브 문자를 추출하고 대문자로 변환
    if drive == 'A:':
        return 'ARBO_BION'
    elif drive == 'B:':
        return 'BTS'        
    elif drive == 'K:':
        return 'CKR'        
    elif drive == 'T:':
        return 'THE_TRAP'
    elif drive == 'S:':
        return 'DSC'        
    elif drive == 'Z:':
        return 'FUZZ'           
    else:
        return 'DSC'  # 기본값

current_project = get_current_project()

def get_project_paths():
    paths = {
        'THE_TRAP': "T:\\",
        'ARBO_BION': "A:\\",
        'BTS': "B:\\",        
        'CKR': "K:\\",
        'DSC': "S:\\",
        'FUZZ': "Z:\\",
        'COC': "S:\\PROJECT\\COC\\02_Production"
    }
    project_path = paths.get(current_project, "")
    return project_path

def get_project_path():
    paths = {
        'THE_TRAP': "T:\\",
        'BTS': "B:\\",        
        'ARBO_BION': "A:\\",
        'CKR': "K:\\",        
        'DSC': "S:\\",
        'FUZZ': "Z:\\",
        'COC': "S:\\PROJECT\\COC\\02_Production"
    }
    return paths

# def get_project_prefix():
    # prefixes = {
        # 'THE_TRAP': "ttm",
        # 'ARBO_BION': "ab",
        # 'DSC': "DSC",
        # 'FUZZ': "FUZZ"        
    # }
    # project_prefix = prefixes.get(current_project, "")
    # return project_prefix

def get_project_prefix():
    prefixes = {
        'THE_TRAP': "ttm",   # 항상 소문자
        'ARBO_BION': "ab",   # 항상 소문자
        'BTS': "BTS",        
        'CKR': "CKR",
        'DSC': "DSC",        # 항상 대문자
        'FUZZ': "fuzz"       # 항상 대문자
    }

    project_prefix = prefixes.get(current_project, "dsc")
    if current_project == "COC":
        return "COC"

    # 🔹 현재 씬 이름에서 프로젝트명 감지 (대소문자 무시)
    scene_path = cmds.file(query=True, sceneName=True)
    file_name = os.path.basename(scene_path).lower()

    # ✅ 씬 파일 이름에 어떤 형태로든 포함되어 있으면 해당 prefix 반환
    for proj, prefix in prefixes.items():
        if prefix.lower() in file_name:
            return prefix  # ← 정의된 형태 그대로 반환

    # 기본값 (로컬 테스트 씬 등)
    return project_prefix




project_paths = get_project_path()

def set_current_project(project):
    global current_project
    current_project = project

def is_coc_project(project_name=None):
    return (project_name or current_project) == "COC"

def get_coc_scene_root():
    return os.path.normpath(os.path.join(get_project_paths(), "Animation", "Detail"))

def get_coc_render_root():
    return os.path.normpath(os.path.join(get_project_paths(), "Rendering"))

def parse_scene_cut_from_filename(file_path):
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    coc_match = re.search(r"(C\d+)[_-](\d+)", base_name, re.IGNORECASE)
    if coc_match:
        return coc_match.group(1), coc_match.group(2)
    parts = base_name.split("_")
    if len(parts) >= 3:
        return parts[1], parts[2]
    return "N/A", "N/A"

def get_coc_browser_context(file_path):
    normalized_path = os.path.normpath(file_path)
    file_name = os.path.basename(normalized_path)
    process = "maya"
    episode_name = "N/A"
    try:
        relative_parts = os.path.relpath(normalized_path, get_coc_scene_root()).split(os.sep)
        if relative_parts:
            episode_name = relative_parts[0]
        if len(relative_parts) >= 2:
            process = relative_parts[1]
    except Exception:
        pass
    return episode_name, "N/A", process, file_name

def get_coc_episode_name(file_path=None):
    file_path = file_path or cmds.file(q=True, sn=True)
    if not file_path:
        return "N/A"
    episode_name, _, _, _ = get_coc_browser_context(file_path)
    return episode_name

def get_cache_dir_path(scene_number, cut_number):
    if is_coc_project():
        episode_name = get_coc_episode_name()
        cut_folder = str(scene_number or "N/A")
        if cut_number and cut_number != "N/A":
            cut_folder = f"{scene_number}_{cut_number}"
        return os.path.normpath(os.path.join(get_coc_render_root(), episode_name, cut_folder, "cache"))
    return os.path.normpath(os.path.join(get_project_paths(), "scenes", scene_number, cut_number, "ren", "cache"))

def get_scene_work_path(scene_name, cut_name, process_name):
    if is_coc_project():
        return os.path.normpath(os.path.join(get_coc_scene_root(), scene_name, process_name))
    return os.path.normpath(os.path.join(get_project_paths(), "scenes", scene_name, cut_name, process_name))

# 파일 경로 분석 함수
def parse_file_path(file_path):
    if is_coc_project():
        return get_coc_browser_context(file_path)
    normalized_path = os.path.normpath(file_path)
    path_parts = normalized_path.split(os.sep)
    if len(path_parts) < 6:
        raise ValueError("The file path does not contain enough parts to extract scene number, cut number, process, and file name.")
    scene_number = path_parts[2]
    cut_number = path_parts[3]
    process = path_parts[4]
    file_name = path_parts[-1]
    return scene_number, cut_number, process, file_name

# 파일 유효성 검사 함수
def is_valid_scene_file(file_path):
    if is_coc_project():
        normalized_file_path = os.path.normpath(file_path)
        return normalized_file_path.startswith(get_coc_scene_root()) and file_path.lower().endswith((".ma", ".mb"))
    try:
        scene_number, cut_number, process, file_name = parse_file_path(file_path)
    except ValueError as e:
        print(f"Invalid file path: {e}")
        return False

    project_path = os.path.normpath(get_project_paths())
    project_prefix = get_project_prefix()
    normalized_file_path = os.path.normpath(file_path)

    if not normalized_file_path.startswith(project_path):
        print(f"File path '{normalized_file_path}' does not start with project path '{project_path}'")
        return False

    # pub 폴더 예외 처리
    if process == 'pub':
        expected_prefix_ani = f"{project_prefix}_{scene_number}_{cut_number}_ani_"
        if file_name.startswith(expected_prefix_ani) and file_name.endswith(".mb"):
            return True

    expected_prefix = f"{project_prefix}_{scene_number}_{cut_number}_{process}_"
    if not file_name.startswith(expected_prefix):
        print(f"File name '{file_name}' does not start with expected prefix '{expected_prefix}'")
        return False
    if not file_name.endswith(".mb"):
        print(f"File name '{file_name}' does not end with '.mb'")
        return False
    return True

# 메뉴 초기화 함수
def clear_option_menu(menu_name):
    menu_items = cmds.optionMenu(menu_name, query=True, itemListLong=True)
    if menu_items:
        for item in menu_items:
            cmds.deleteUI(item)

def filter_folders(folders):
    return [f for f in folders if not (f.startswith('_') or f.startswith('.'))]

def update_scenes(*args):
    global current_project
    current_project = cmds.optionMenu(projectMenuName, query=True, value=True)
    project_path = project_paths.get(current_project, "")
    
    clear_option_menu('sceneMenu')
    clear_option_menu('cutMenu')
    clear_option_menu('processMenu')
    clear_option_menu('fileMenu')

    if project_path:
        scenes_path = get_coc_scene_root() if is_coc_project() else os.path.join(project_path, 'scenes')
        scenes = sorted(filter_folders(os.listdir(scenes_path)))
        if scenes:
            for scene in scenes:
                cmds.menuItem(parent='sceneMenu', label=scene)
            update_cuts()
        else:
            cmds.menuItem(parent='sceneMenu', label='No scenes available')

def update_cuts(*args, selected_scene=None):
    global current_project
    current_project = cmds.optionMenu(projectMenuName, query=True, value=True)
    project_path = project_paths.get(current_project, "")
    
    current_scene = selected_scene if selected_scene else cmds.optionMenu('sceneMenu', query=True, value=True)
    
    clear_option_menu('cutMenu')
    clear_option_menu('processMenu')
    clear_option_menu('fileMenu')

    if project_path and current_scene and current_scene != 'No scenes available':
        if is_coc_project():
            cmds.menuItem(parent='cutMenu', label='N/A')
            update_processes(selected_cut='N/A')
        else:
            cuts = sorted(filter_folders(os.listdir(os.path.join(project_path, 'scenes', current_scene))))
            if cuts:
                for cut in cuts:
                    cmds.menuItem(parent='cutMenu', label=cut)
                update_processes(selected_cut=None)
            else:
                cmds.menuItem(parent='cutMenu', label='No cuts available')

def incremental_save():
    change_description = cmds.textField(changeDescriptionField, query=True, text=True)  # 텍스트 필드의 내용을 가져옵니다.
    change_description = change_description.replace(" ", "_")  # 공백을 언더바로 교체합니다.

    current_file = cmds.file(q=True, sn=True)
    if not current_file:
        cmds.warning("No file is currently open.")
        return

    # 파일 이름에서 이전 변경사항을 제거하는 로직 추가
    # 예: check_rig_v030_material_wheel.mb -> check_rig_v030_wheel.mb
    base_name_pattern = re.compile(r"(.+)(_v\d+)(_.+)?(\.mb)$")
    match = base_name_pattern.search(current_file)
    if match:
        base_name = match.group(1)  # 기본 이름 (예: check_rig)
        version_str = match.group(2)  # 버전 (예: _v030)
        file_ext = match.group(4)  # 파일 확장자 (예: .mb)
        version_num = int(version_str[2:])  # 숫자 부분만 추출 (예: 30)
        new_version_num = version_num + 1  # 버전 1 증가
        new_version_str = "v" + str(new_version_num).zfill(3)  # 새 버전 문자열 (예: _v031)

        # 새로운 파일 이름 구성: 기본 이름 + 새 버전 + 변경사항 + 확장자
        new_file_name = f"{base_name}_{new_version_str}"
        if change_description:  # 변경사항이 입력되었다면 파일 이름에 추가
            new_file_name += f"_{change_description}"
        new_file_name += file_ext  # 파일 확장자 추가

        cmds.file(rename=new_file_name)
        cmds.file(save=True, type='mayaBinary')
        return new_file_name
    else:
        cmds.warning("Version information not found in file name.")
        return None

def update_processes(*args, selected_cut=None):
    global current_project
    current_project = cmds.optionMenu(projectMenuName, query=True, value=True)
    project_path = project_paths.get(current_project, "")
    
    current_scene = cmds.optionMenu('sceneMenu', query=True, value=True)
    current_cut = selected_cut if selected_cut else cmds.optionMenu('cutMenu', query=True, value=True)
    
    clear_option_menu('processMenu')
    clear_option_menu('fileMenu')
    
    if project_path and current_scene and current_cut and current_scene != 'No scenes available' and current_cut != 'No cuts available':
        if is_coc_project():
            cmds.menuItem(parent='processMenu', label='maya')
            update_files(selected_process='maya')
        else:
            processes_path = os.path.join(project_path, 'scenes', current_scene, current_cut)
            if os.path.exists(processes_path):
                processes = sorted([d for d in os.listdir(processes_path) if os.path.isdir(os.path.join(processes_path, d))])
                if processes:
                    for process in processes:
                        cmds.menuItem(parent='processMenu', label=process)
                    update_files(selected_process=None)
                else:
                    cmds.menuItem(parent='processMenu', label='No processes available')
            else:
                cmds.menuItem(parent='processMenu', label='No processes available')

def update_files(*args, selected_process=None):
    global current_project
    project_path = project_paths.get(current_project, "")
    
    current_scene = cmds.optionMenu('sceneMenu', query=True, value=True)
    current_cut = cmds.optionMenu('cutMenu', query=True, value=True)
    current_process = selected_process if selected_process else cmds.optionMenu('processMenu', query=True, value=True)
    clear_option_menu('fileMenu')

    # ✅ Fin 특별 처리
    if current_process == "Fin":
        category = current_scene
        asset_name = current_cut
        if category and asset_name and category != 'No scenes available' and asset_name != 'No cuts available':
            fin_file_path = os.path.join(project_path, "assets", category, asset_name, f"{asset_name}.mb")
            if os.path.exists(fin_file_path):
                cmds.menuItem(parent='fileMenu', label=f"{asset_name}.mb")
            else:
                cmds.menuItem(parent='fileMenu', label='No files found')
        else:
            cmds.menuItem(parent='fileMenu', label='No files found')

    else:
        # ✅ 일반 프로세스 처리
        if project_path and current_scene and current_cut and current_process and \
           current_scene != 'No scenes available' and current_cut != 'No cuts available' and current_process != 'No processes available':
            files_path = get_scene_work_path(current_scene, current_cut, current_process)
            if os.path.exists(files_path):
                files = sorted(
                    [f for f in os.listdir(files_path) if os.path.isfile(os.path.join(files_path, f)) and f.lower().endswith(('.ma', '.mb'))],
                    key=lambda f: os.path.getmtime(os.path.join(files_path, f)),
                    reverse=True
                )
                if files:
                    for file in files:
                        cmds.menuItem(parent='fileMenu', label=file)
                else:
                    cmds.menuItem(parent='fileMenu', label='No files found')
            else:
                cmds.menuItem(parent='fileMenu', label='No files found')
        else:
            cmds.menuItem(parent='fileMenu', label='No files found')

    # 🔥 상태 저장 (마지막에 강제 저장)
    selected_file = cmds.optionMenu('fileMenu', q=True, value=True)
    if selected_file and selected_file not in ('No files found', 'No files available'):
        save_browser_state(current_project, current_scene, current_cut, current_process, selected_file)




# 현재 파일을 기반으로 메뉴 업데이트 함수
def update_menus_from_current_file():
    current_file_path = cmds.file(query=True, sceneName=True)
    if not current_file_path:
        cmds.warning("No file is currently open.")
        return
    if not is_valid_scene_file(current_file_path):
        cmds.warning("The current file does not meet the project criteria.")
        return
    try:
        scene_number, cut_number, process, file_name = parse_file_path(current_file_path)
    except Exception as e:
        print(f"Error parsing file path: {e}")
        return

    cmds.optionMenu('sceneMenu', edit=True, deleteAllItems=True)
    cmds.menuItem(label=scene_number, parent='sceneMenu')
    update_cuts(selected_scene=scene_number)

    cut_menu_items = [item for item in cmds.optionMenu('cutMenu', query=True, itemListLong=True)]
    if cut_number in [cmds.menuItem(item, query=True, label=True) for item in cut_menu_items]:
        cmds.optionMenu('cutMenu', edit=True, value=cut_number)
    update_processes(selected_cut=cut_number)

    process_menu_items = [item for item in cmds.optionMenu('processMenu', query=True, itemListLong=True)]
    if process in [cmds.menuItem(item, query=True, label=True) for item in process_menu_items]:
        cmds.optionMenu('processMenu', edit=True, value=process)
    update_files(selected_process=process)

    cmds.optionMenu('fileMenu', edit=True, deleteAllItems=True)
    cmds.menuItem(label=file_name, parent='fileMenu')

def open_selected_file(*args):
    global current_project
    project_path = project_paths.get(current_project, "")
    current_scene = cmds.optionMenu('sceneMenu', query=True, value=True)
    current_cut = cmds.optionMenu('cutMenu', query=True, value=True)
    current_process = cmds.optionMenu('processMenu', query=True, value=True)
    selected_file = cmds.optionMenu('fileMenu', query=True, value=True)
    
    if project_path and current_scene and current_cut and current_process and selected_file and selected_file != 'No files available':
        file_path = os.path.join(get_scene_work_path(current_scene, current_cut, current_process), selected_file)
        if os.path.exists(file_path):
            cmds.file(file_path, open=True, force=True)
            
def load_selected_asset(action):
    global current_project
    project_path = project_paths.get(current_project, "")
    selected_project = cmds.optionMenu(projectMenuName, query=True, value=True)
    current_scene = cmds.optionMenu('sceneMenu', query=True, value=True)
    current_cut = cmds.optionMenu('cutMenu', query=True, value=True)
    current_process = cmds.optionMenu('processMenu', query=True, value=True)
    selected_file = cmds.optionMenu('fileMenu', query=True, value=True)

    if project_path and current_scene and current_cut and current_process and selected_file:
        file_path = os.path.join(get_scene_work_path(current_scene, current_cut, current_process), selected_file)
        if os.path.exists(file_path):
            if action == "open":
                cmds.file(file_path, o=True, force=True, ignoreVersion=True)
            elif action == "reference":
                cmds.file(file_path, r=True, options="v=0")
            else:
                cmds.warning(f"Unsupported action: {action}")
        else:
            cmds.warning(f"Asset path does not exist: {file_path}")

def clear_option_menu_items(option_menu):
    menu_items = cmds.optionMenu(option_menu, query=True, itemListLong=True)
    if menu_items:
        for item in menu_items:
            cmds.deleteUI(item)

def get_subfolder_names(directory, exclude_word='light'):
    try:
        subfolders = [name for name in os.listdir(directory) 
                      if os.path.isdir(os.path.join(directory, name)) and exclude_word not in name]
        return subfolders
    except OSError as e:
        print(f"Error: Failed to access directory '{directory}'. Exception: {e}")
        return []

base_path = get_project_paths()
character_dir = os.path.join(base_path, "assets", "ch")
background_dir = os.path.join(base_path, "assets", "bg")
prop_dir = os.path.join(base_path, "assets", "prop")

CHARACTER_NAMES = get_subfolder_names(character_dir)
BG_NAMES = get_subfolder_names(background_dir)
PROP_NAMES = get_subfolder_names(prop_dir)

# 현재 파일 이름 분석
current_file_name = os.path.basename(cmds.file(q=True, sn=True))
is_ttm = current_file_name.startswith("ttm_")

if is_ttm:
    # 예외 프랍 조건: hatch와 floor는 제외
    additional_prop_names = [
        name for name in BG_NAMES
        if (name.startswith('control') or name in ['glassDoor', 'water', 'button'])
           and not name.startswith('floor') and name != 'hatch'
    ]

    PROP_NAMES += additional_prop_names

    # BG에서 제외할 항목 정의 (floor*, hatch는 제외)
    exclude_from_bg = additional_prop_names
    BG_NAMES = [name for name in BG_NAMES if name not in exclude_from_bg]

    # print(f"[INFO] ttm 파일: 다음 BG 항목이 프랍으로 이동됨 → {additional_prop_names}")
# else:
    # print("[INFO] 일반 파일: PROP_NAMES는 prop 디렉토리 기준으로만 사용됩니다.")


# def get_scene_cut_camera():
    # cameras = cmds.ls(type='camera')
    # for camera in cameras:
        # transform = cmds.listRelatives(camera, parent=True)[0]
        # transform_no_namespace = transform.split(":")[-1]
        # if transform_no_namespace.startswith("cam_"):
            # parts = transform_no_namespace.split("_")
            # if len(parts) == 3:
                # return transform
    # return None

def get_scene_cut_camera():
    """씬 내 카메라 자동 탐색 (기존 cam_패턴 + prefix_cam 패턴 모두 지원)"""
    cameras = cmds.ls(type='camera')
    if not cameras:
        return None

    prefix_lower = get_project_prefix().lower()

    for camera in cameras:
        transform = cmds.listRelatives(camera, parent=True)[0]
        transform_no_namespace = transform.split(":")[-1]
        name_lower = transform_no_namespace.lower()

        # ✅ 1️⃣ 기존 cam_씬컷 구조 유지
        if name_lower.startswith("cam_"):
            parts = name_lower.split("_")
            if len(parts) == 3:
                return transform

        # ✅ 2️⃣ 확장: fuzz_xxx_cam / ttm_xxx_cam / ab_xxx_cam 등 허용
        if name_lower.startswith(prefix_lower + "_") and name_lower.endswith("_cam"):
            return transform

    cmds.warning(f"[⚠️] '{prefix_lower}_..._cam' 혹은 'cam_###_###' 형태의 카메라를 찾지 못했습니다.")
    return None


def get_scene_and_cut():
    file_path = cmds.file(q=True, sn=True)
    if is_coc_project():
        return parse_scene_cut_from_filename(file_path)
    file_name = file_path.split("/")[-1]
    parts = file_name.split("_")
    if len(parts) >= 4:
        scene = parts[1]
        cut = parts[2]
    else:
        scene = "N/A"
        cut = "N/A"
    return scene, cut

scene_number, cut_number = get_scene_and_cut()

def get_export_status(asset_name, category, scene_number, cut_number):
    project_prefix = get_project_prefix()
    cache_dir = get_cache_dir_path(scene_number, cut_number)

    if category == 'cam':
        paths = [
            os.path.join(cache_dir, f"{project_prefix}_{scene_number}_{cut_number}_cam.fbx")
        ]
    else:
        paths = [
            os.path.join(cache_dir, f"{project_prefix}_{scene_number}_{cut_number}_{category}_{asset_name}.usd"),
            os.path.join(cache_dir, f"{project_prefix}_{scene_number}_{cut_number}_anim_{asset_name}.json"),
            os.path.join(cache_dir, f"{project_prefix}_{scene_number}_{cut_number}_{category}_{asset_name}.fbx"),
            os.path.join(cache_dir, f"{project_prefix}_{scene_number}_{cut_number}_{category}_{asset_name}.abc")
        ]

    existing_files = [path for path in paths if os.path.exists(path)]
    if not existing_files:
        return False, None

    latest_file = max(existing_files, key=os.path.getmtime)
    mod_time = os.path.getmtime(latest_file)
    formatted_date = time.strftime("%y%m%d", time.localtime(mod_time))
    formatted_time = time.strftime("%H:%M", time.localtime(mod_time))
    return True, f"{formatted_date} {formatted_time}"



def get_camera_export_status(scene_number, cut_number):
    project_prefix = get_project_prefix()
    export_path = os.path.join(get_cache_dir_path(scene_number, cut_number), f"{project_prefix}_{scene_number}_{cut_number}_cam.fbx")
    if os.path.exists(export_path):
        mod_time = os.path.getmtime(export_path)
        formatted_date = time.strftime("%y%m%d", time.localtime(mod_time))
        formatted_time = time.strftime("%H:%M", time.localtime(mod_time))
        return True, f"{formatted_date} {formatted_time}"
    else:
        return False, None

def open_cache_folder(scene_number, cut_number):
    cache_folder_path = get_cache_dir_path(scene_number, cut_number)
    if os.path.exists(cache_folder_path):
        subprocess.Popen(f'explorer "{cache_folder_path}"')
    else:
        cmds.warning(f"Cache folder does not exist: {cache_folder_path}")

def open_scene_folder():
    global current_project
    project_path = project_paths.get(current_project, "")
    current_scene = cmds.optionMenu('sceneMenu', query=True, value=True)
    current_cut = cmds.optionMenu('cutMenu', query=True, value=True)
    current_process = cmds.optionMenu('processMenu', query=True, value=True)
    selected_file = cmds.optionMenu('fileMenu', query=True, value=True)
    if project_path and current_scene and current_cut and current_process and selected_file:
        file_folder = get_scene_work_path(current_scene, current_cut, current_process)
        if os.path.exists(file_folder):
            if os.name == 'nt':  # If the operating system is Windows
                subprocess.Popen(f'explorer "{file_folder}"')
            elif os.name == 'posix':  # If the operating system is Linux/MacOS
                subprocess.Popen(['open', file_folder])
            else:
                cmds.warning("Unsupported operating system.")
        else:
            cmds.warning(f"Asset folder does not exist: {file_folder}")

def get_namespace_group(namespace):
    match = re.match(r'^([a-zA-Z]+)(\d*)$', namespace)
    if match:
        base = match.group(1)
        return base
    return namespace

def find_characters_in_scene():
    all_groups = cmds.ls(long=True, dag=True, type='transform')
    found_characters = {}
    name_counts = {}

    for group in all_groups:
        short_name = group.split('|')[-1]
        base_name = short_name.split(':')[-1]  # 네임스페이스 제거

        # ✅ 캐릭터 이름과 완전 일치하는 경우만 허용
        if base_name not in CHARACTER_NAMES:
            continue

        if not cmds.getAttr(group + ".visibility"):
            continue

        children = cmds.listRelatives(group, children=True, fullPath=True, type='transform') or []
        geo_group = next((c for c in children if c.split('|')[-1].endswith('geo')), None)
        if not geo_group:
            continue

        key = base_name if base_name not in name_counts else f"{base_name}_{name_counts[base_name]+1}"
        name_counts[base_name] = name_counts.get(base_name, 0) + 1
        found_characters[key] = group

    return found_characters



def find_bgs_in_scene():
    all_groups = cmds.ls(long=True, dag=True, type='transform')
    found_bgs = {}
    name_counts = {}

    bg_names_lower = [n.lower() for n in BG_NAMES]

    for group in all_groups:
        short_name = group.split('|')[-1]
        namespace_parts = short_name.split(':')
        base_name = namespace_parts[-1]

        if base_name.lower() in bg_names_lower or any(base_name.lower().startswith(n) for n in bg_names_lower):
            is_visible = cmds.getAttr(group + ".visibility")
            if is_visible:
                children = cmds.listRelatives(group, children=True, fullPath=True, type='transform')
                if children:
                    geo_group = next((child for child in children if child.endswith('geo')), None)
                    if geo_group:
                        if base_name in name_counts:
                            name_counts[base_name] += 1
                            unique_name = f"{base_name}_{name_counts[base_name]}"
                        else:
                            name_counts[base_name] = 1
                            unique_name = base_name

                        # ✅ 여기서 group 경로 전체를 저장해야 나중에 cmds.select() 가능
                        found_bgs[unique_name] = group

    return found_bgs


def normalize_name(name):
    """네임스페이스 제거 + 언더스코어 중복 토큰/geo 정리"""
    clean = name.split(':')[-1]   # 네임스페이스 제거
    parts = clean.split('_')

    # 중복 토큰 제거 (ex: foo_foo → foo)
    unique_parts = []
    for p in parts:
        if not unique_parts or unique_parts[-1].lower() != p.lower():
            unique_parts.append(p)

    # 마지막 토큰이 geo 변형일 경우 → geo로 치환
    if unique_parts[-1].lower() == "geo":
        return "geo"

    return '_'.join(unique_parts)


def has_geo_child(group):
    """group 밑에 geo(네임스페이스/_ 변형 포함) 있는지 검사"""

    # 만약 unique_name(가짜 이름)이 들어왔다면 → dict에서 실제 경로 찾아 교체
    if not cmds.objExists(group):
        # Prop 선택 dict 확인
        if group in selected_prop_paths:
            group = selected_prop_paths[group]
        # Prop UI 참조 dict 확인
        elif group in prop_button_refs:
            data = prop_button_refs[group]
            group = data[1] if isinstance(data, tuple) else data

        # Character / BG 도 동일 패턴 (버튼 참조 dict에서 풀패스 꺼냄)
        elif group in character_button_refs:
            data = character_button_refs[group]
            group = data[1] if isinstance(data, tuple) else data
        elif group in bg_button_refs:
            data = bg_button_refs[group]
            group = data[1] if isinstance(data, tuple) else data

        else:
            cmds.warning(f"[has_geo_child] 잘못된 이름 전달됨: {group}")
            return None

    # 이제 group 은 DAG 경로일 것
    children = cmds.listRelatives(group, children=True, fullPath=True, type='transform')
    if not children:
        return None

    for child in children:
        if normalize_name(child).lower() == "geo":
            return child  # 실제 경로 반환
    return None



def find_props_in_scene():
    """
    씬 안의 프랍들을 찾아 고유 이름(unique_name)으로 매핑한다.
    - 기본은 baseName 그대로
    - 동일 프랍이 여러 개면 _1, _2 번호를 추가
    """
    found_props = {}
    name_counts = {}

    prop_names_lower = [p.lower() for p in PROP_NAMES]
    all_groups = cmds.ls(long=True, type="transform")

    for group in all_groups:
        short_name = group.split('|')[-1]
        base_name = normalize_name(short_name)

        if base_name.lower() not in prop_names_lower:
            continue

        # base_name 단위로 카운트
        count = name_counts.get(base_name, 0)

        if count == 0:
            unique_name = base_name
        else:
            unique_name = f"{base_name}_{count}"

        name_counts[base_name] = count + 1

        geo_group = has_geo_child(group)
        if geo_group:
            found_props[unique_name] = group

    return found_props




# def export_character(character_name, scene_number, cut_number):
    # characters_in_scene = find_characters_in_scene()
    # geo_group = characters_in_scene.get(character_name)
    # if not geo_group:
        # print(f"{character_name}에 해당하는 지오메트리 그룹을 찾을 수 없습니다.")
        # return
    # min_time = cmds.optionMenu('minTimeMenu', query=True, value=True)
    # result = export_usd(character_name, geo_group, scene_number, cut_number, int(min_time))
    # if result:
        # print(f"{character_name} 익스포트가 성공적으로 완료되었습니다.")
    # else:
        # print(f"{character_name} 익스포트에 실패했습니다.")
    # #rrAnimout_UI()
    
    
def export_character(character_name, scene_number, cut_number):
    # ✅ UI 매핑 먼저 확인
    geo_group = selected_character_paths.get(character_name)

    # ✅ 없으면 fallback
    if not geo_group:
        characters_in_scene = find_characters_in_scene()
        geo_group = characters_in_scene.get(character_name)

    if not geo_group:
        print(f"{character_name}에 해당하는 지오메트리 그룹을 찾을 수 없습니다.")
        return

    clean_name = remove_namespace(geo_group)  # ← 'crimson4:crimson' → 'crimson'

    min_time = int(cmds.optionMenu('minTimeMenu', query=True, value=True))
    result = export_usd(clean_name, geo_group, scene_number, cut_number, min_time)
    if result:
        print(f"{clean_name} 익스포트가 성공적으로 완료되었습니다.")
    else:
        print(f"{clean_name} 익스포트에 실패했습니다.")


def export_prop(prop_name, scene_number, cut_number):
    props_in_scene = find_props_in_scene()
    geo_group = props_in_scene.get(prop_name)
    if not geo_group:
        print(f"{prop_name}에 해당하는 지오메트리 그룹을 찾을 수 없습니다.")
        return
    result = export_usd_prop(scene_number, cut_number, prop_name, geo_group)
    if result:
        print(f"{prop_name} 익스포트가 성공적으로 완료되었습니다.")
    else:
        print(f"{prop_name} 익스포트에 실패했습니다.")
    #rrAnimout_UI()

def export_bgs(bg_name, scene_number, cut_number):
    bgs_in_scene = find_bgs_in_scene()
    geo_group = bgs_in_scene.get(bg_name)
    if not geo_group:
        print(f"{bg_name}에 해당하는 지오메트리 그룹을 찾을 수 없습니다.")
        return
    result = export_usd_bg(bg_name, geo_group, scene_number, cut_number)
    if result:
        print(f"{bg_name} 익스포트가 성공적으로 완료되었습니다.")
    else:
        print(f"{bg_name} 익스포트에 실패했습니다.")
    #rrAnimout_UI()
    
def export_all_characters():
    characters_in_scene = find_characters_in_scene()
    success = True
    min_time = int(cmds.optionMenu('minTimeMenu', query=True, value=True))

    for unique_name, group_path in characters_in_scene.items():
        result = export_usd(unique_name, group_path, *get_scene_and_cut(), min_time)
        if not result:
            success = False

    if success:
        print("캐릭터 익스포트가 정상적으로 끝났습니다")
    else:
        print("하나 이상의 캐릭터 익스포트가 실패했습니다")



def export_all_props():
    props_in_scene = find_props_in_scene()
    scene_number, cut_number = get_scene_and_cut()
    success = True

    for unique_name, group_path in props_in_scene.items():
        result = export_usd_prop(scene_number, cut_number, unique_name, group_path)
        if not result:
            success = False

    if success:
        print("프랍 익스포트가 정상적으로 끝났습니다")
    else:
        print("하나 이상의 프랍 익스포트가 실패했습니다")




def toggle_viewport(show):
    model_panels = cmds.getPanel(type='modelPanel')
    for panel in model_panels:
        if show:
            cmds.modelEditor(panel, edit=True, allObjects=True)
        else:
            cmds.modelEditor(panel, edit=True, allObjects=False)
        
def export_alembic(character_name, character_geo, scene_number, cut_number):
    with EvalModeGuard('off'):
        toggle_viewport(False)
        cmds.select(character_geo, replace=True)
        if not character_geo:
            cmds.warning(f"No geo group found for character.")
            return False
        duplicated = cmds.duplicate(rr=True, ic=True)[0]
        base_path = get_project_paths()
        export_path = get_cache_dir_path(str(scene_number), str(cut_number))
        if not os.path.exists(export_path):
            os.makedirs(export_path)
        project_prefix = get_project_prefix()
        file_name = f"{project_prefix}_{scene_number}_{cut_number}_{character_name}.abc"
        full_export_path = os.path.join(export_path, file_name)
        minTime = cmds.playbackOptions(query=True, minTime=True)
        maxTime = cmds.playbackOptions(query=True, maxTime=True)
        export_cmd = f'-frameRange {minTime} {maxTime} -uvWrite -writeColorSets -writeFaceSets -wholeFrameGeo -worldSpace -writeVisibility -autoSubd -sn 1 -writeUVSets -dataFormat ogawa -root {duplicated} -file "{full_export_path}"'
        cmds.AbcExport(j=export_cmd)
        cmds.delete(duplicated)
        toggle_viewport(True)
        return True


def remove_namespace(name):
    return name.split(':')[-1]

def get_unique_name(base_name, existing_names):
    counter = 1
    new_name = base_name
    while new_name in existing_names:
        new_name = f"{base_name}{counter:02d}"
        counter += 1
    return new_name

def export_selected_to_usd():
    print("Starting export process")
    scene_number, cut_number = get_scene_and_cut()
    minTime = int(cmds.playbackOptions(query=True, minTime=True))
    maxTime = int(cmds.playbackOptions(query=True, maxTime=True))
    selected_folders = cmds.ls(selection=True, type='transform')
    if not selected_folders:
        cmds.warning("No folders selected.")
        return False

    toggle_viewport(False)
    exported_names = set()
    for prop_folder in selected_folders:
        asset_name = remove_namespace(prop_folder)
        geo_candidates = cmds.ls(f"{prop_folder}|*geo", long=True)
        if not geo_candidates:
            cmds.warning(f"No 'geo' object found in folder: {prop_folder}.")
            continue
        geo = geo_candidates[0]

        unique_name = get_unique_name(asset_name, exported_names)
        exported_names.add(unique_name)

        try:
            duplicated = cmds.duplicate(geo, rr=True, ic=True)[0]

            # ✅ 안전하게 월드로 옮기기
            try:
                parent = cmds.listRelatives(duplicated, parent=True, fullPath=True)
                if parent:
                    cmds.parent(duplicated, world=True)
            except Exception as e:
                print(f"[Warning] Failed to parent {duplicated}: {e}")

            local_cache_path = os.path.join(os.getenv('TEMP'), 'MayaUSDExport')
            os.makedirs(local_cache_path, exist_ok=True)
            file_name = f"{get_project_prefix()}_{scene_number}_{cut_number}_prop_{unique_name}.usd"
            local_file_path = os.path.join(local_cache_path, file_name)

            usd_options = (
                f';exportUVs=1;exportSkels=none;exportSkin=none;exportBlendShapes=0;'
                f'exportDisplayColor=0;filterTypes=nurbsCurve;exportColorSets=0;exportComponentTags=1;'
                f'defaultMeshScheme=none;animation=1;eulerFilter=0;staticSingleSample=0;startTime={minTime};'
                f'endTime={maxTime};frameStride=1;frameSample=0.0;defaultUSDFormat=usdc;'
                f'parentScope={unique_name};shadingMode=useRegistry;convertMaterialsTo=[UsdPreviewSurface];'
                f'exportInstances=1;exportVisibility=1;mergeTransformAndShape=1;stripNamespaces=0;worldspace=1'
            )

            cmds.select(duplicated)
            cmds.bakeResults(duplicated, t=(minTime, maxTime), shape=True)
            cmds.file(local_file_path, force=True, options=usd_options, type="USD Export", pr=True, es=True)

            network_path = get_cache_dir_path(scene_number, cut_number)
            os.makedirs(network_path, exist_ok=True)
            shutil.copy(local_file_path, os.path.join(network_path, file_name))
            os.remove(local_file_path)
            cmds.delete(duplicated)
        except Exception as e:
            cmds.warning(f"[ERROR] {unique_name} export failed: {e}")
            continue

    toggle_viewport(True)
    refresh_animout_ui('prop')
    return True


def bake_cha(character_name):
    toggle_viewport(False)
    # 캐릭터 그룹 하위에서 headTip_skin을 검색합니다.
    headTipSkins = cmds.ls(f"*:{character_name}:*|*headTip_skin", r=True) + cmds.ls(f"*:{character_name}_*|*headTip_skin", r=True)
    
    if headTipSkins:
        minTime = 90
        maxTime = cmds.playbackOptions(query=True, maxTime=True)
        cmds.currentTime(minTime)
        for headTipSkin in headTipSkins:
            cmds.select(headTipSkin)
            cmds.bakeResults(simulation=True, hi="below", t=(minTime, maxTime))
        print(f"headTip_skin baked for character: {character_name}")
    else:
        print(f"No headTip_skin found for character: {character_name}, skipping bake.")
    toggle_viewport(True)

def get_next_geo_name(base_name="geo"):
    i = 1
    while cmds.objExists(f"{base_name}_{i:03d}"):
        i += 1
    return f"{base_name}_{i:03d}"


# 디스플레이 레이어 이름을 변경하는 함수
def rename_display_layer_if_exists(base_name='geo'):
    # 'geo'라는 이름의 디스플레이 레이어가 존재하는지 확인
    if cmds.ls(base_name, type='displayLayer'):
        suffix = 1
        # 중복된 이름이 있는지 확인하고, 고유한 이름 생성
        while cmds.ls(f'{base_name}{suffix}', type='displayLayer'):
            suffix += 1
        new_name = f'{base_name}{suffix}'
    else:
        new_name = base_name
    
    # 디스플레이 레이어 이름 변경
    cmds.rename(base_name, new_name)
    return new_name


import maya.cmds as cmds
import os
import shutil

# 디스플레이 레이어 이름을 변경하는 함수
def rename_display_layer_if_exists(base_name='geo'):
    # 'geo'라는 이름의 디스플레이 레이어가 존재하는지 확인
    if cmds.ls(base_name, type='displayLayer'):
        suffix = 1
        # 중복된 이름이 있는지 확인하고, 고유한 이름 생성
        while cmds.ls(f'{base_name}{suffix}', type='displayLayer'):
            suffix += 1
        new_name = f'{base_name}{suffix}'
    else:
        new_name = base_name
    
    # 디스플레이 레이어 이름 변경
    cmds.rename(base_name, new_name)
    return new_name


# 디스플레이 레이어 이름을 변경하는 함수
def rename_display_layer_if_exists(base_name='geo'):
    # 'geo'라는 이름의 디스플레이 레이어가 존재하는지 확인
    if not cmds.ls(base_name, type='displayLayer'):
        # 만약 존재하지 않는다면 함수를 종료하고 아무 작업도 하지 않음
        print(f"No display layer named '{base_name}' found. Skipping rename.")
        return base_name
    
    # 중복된 이름이 있는지 확인하고, 고유한 이름 생성
    suffix = 1
    while cmds.ls(f'{base_name}{suffix}', type='displayLayer'):
        suffix += 1
    new_name = f'{base_name}{suffix}'
    
    # 디스플레이 레이어 이름 변경
    cmds.rename(base_name, new_name)
    return new_name


def cleanup_existing_geo_node():
    """
    월드 루트에 있는 'geo' 노드나 displayLayer를 삭제 또는 이름 변경하여 충돌 방지
    """
    # 월드에 존재하는 transform 노드 'geo' 삭제
    if cmds.objExists("geo") and cmds.nodeType("geo") == "transform":
        try:
            cmds.delete("geo")
            print("[CLEANUP] 기존 'geo' transform 노드 삭제됨")
        except Exception as e:
            cmds.warning(f"[CLEANUP] 'geo' 노드 삭제 실패: {e}")

    # displayLayer가 'geo' 이름일 경우 → 이름 변경
    if cmds.objExists("geo") and cmds.nodeType("geo") == "displayLayer":
        try:
            new_layer_name = "geo_displayLayer_old"
            if cmds.objExists(new_layer_name):
                cmds.delete(new_layer_name)
            cmds.rename("geo", new_layer_name)
            print(f"[CLEANUP] 'geo' displayLayer → '{new_layer_name}' 로 이름 변경")
        except Exception as e:
            cmds.warning(f"[CLEANUP] displayLayer 이름 변경 실패: {e}")


# 🔹 ε 모디파이어 보조 함수 (파일 상단 유틸 영역에 추가)
def _list_live_meshes(root):
    shapes = cmds.listRelatives(root, ad=True, type='mesh', f=True) or []
    return [(cmds.listRelatives(s, p=True, f=True)[0], s)
            for s in shapes if not cmds.getAttr(s + ".intermediateObject")]

def _force_timesamples_with_cluster(geo_root, t_start, t_end, eps=1e-5):
    pairs = _list_live_meshes(geo_root)
    if not pairs:
        print(f"[WARN] '{geo_root}' 하위에 mesh 없음.")
        return
    t_mid = (t_start + t_end) * 0.5
    clusters = []
    for xf, shp in pairs:
        try:
            deformer, handle = cmds.cluster(shp + ".vtx[*]", n="__tsCLS__#", rel=True)
            clusters.append((deformer, handle))
            cmds.setAttr(handle + ".tx", 0.0)
            cmds.setKeyframe(handle + ".tx", t=t_start, v=0.0)
            cmds.setKeyframe(handle + ".tx", t=t_mid, v=eps)
            cmds.setKeyframe(handle + ".tx", t=t_end, v=0.0)
        except:
            pass
    cmds.bakeResults(geo_root, t=(t_start, t_end), shape=True)
    for d, h in clusters:
        if cmds.objExists(d):
            cmds.delete([d, h])
    print(f"[INFO] ε 클러스터 트릭 완료 (ε={eps})")



def export_usd(character_name, character_group, scene_number, cut_number, minTime):
    """
    캐릭터 그룹 하위의 'geo'만 복사해서 USD로 익스포트.
    이름은 항상 'geo'로 고정, headTip_skin 베이크 포함.
    실패해도 정리/복원 안전하게 처리됨.
    (⚙️ 원래 구조 그대로, 선택 로직 절대 건드리지 않음)
    """
    with EvalModeGuard('off'):  # DG 모드 전환
        toggle_viewport(False)

        bake_cha(character_name)

        # 💧 사전 정리
        if cmds.objExists("geo") and cmds.nodeType("geo") == "transform":
            try:
                cmds.delete("geo")
            except:
                pass

        if cmds.objExists("geo") and cmds.nodeType("geo") == "displayLayer":
            try:
                new_layer_name = "geo_displayLayer_old"
                if cmds.objExists(new_layer_name):
                    cmds.delete(new_layer_name)
                cmds.rename("geo", new_layer_name)
            except:
                pass

        # 🎯 geo 찾기 (has_geo_child 사용)
        geo_node = has_geo_child(character_group)
        if not geo_node:
            cmds.warning(f"[ERROR] '{character_group}' 하위에 'geo' 그룹이 없습니다.")
            toggle_viewport(True)
            return False

        # ✨ 복제 및 월드로 언패런트
        try:
            duplicated_geo = cmds.duplicate(geo_node, rr=True, ic=True)[0]
            parent = cmds.listRelatives(duplicated_geo, parent=True, fullPath=True)
            if parent:
                cmds.parent(duplicated_geo, world=True)
        except Exception as e:
            cmds.warning(f"[ERROR] 복제 또는 언패런트 실패: {e}")
            toggle_viewport(True)
            return False

        # 🏷️ 이름 고정
        if duplicated_geo != "geo":
            if cmds.objExists("geo"):
                try:
                    cmds.delete("geo")
                except:
                    pass
            try:
                duplicated_geo = cmds.rename(duplicated_geo, "geo")
            except:
                toggle_viewport(True)
                return False

        success = False
        try:
            endTime = cmds.playbackOptions(q=True, max=True)

            # ✅ 기존 베이크
            cmds.bakeResults("geo", t=(minTime, endTime), shape=True)

            # 🔥 ε-모디파이어 트릭 적용 (정적이라도 애니로 인식)
            _force_timesamples_with_cluster("geo", minTime, endTime, eps=1e-5)

            # ✅ 선택 상태 복원 (원본처럼 geo가 선택된 상태로 유지)
            cmds.select(clear=True)
            cmds.select("geo", r=True)

            file_name = f"{get_project_prefix()}_{scene_number}_{cut_number}_ch_{character_name}.usd"
            local_cache_path = os.path.normpath(os.path.join(os.getenv('TEMP'), 'MayaUSDExport'))
            local_file_path = os.path.normpath(os.path.join(local_cache_path, file_name))
            os.makedirs(local_cache_path, exist_ok=True)

            # USD Export 옵션 (staticSingleSample=0 유지)
            usd_options = (
                f';exportUVs=1;exportSkels=none;exportSkin=none;exportBlendShapes=0;'
                f'exportDisplayColor=0;filterTypes=nurbsCurve;exportColorSets=0;'
                f'defaultMeshScheme=none;animation=1;eulerFilter=0;staticSingleSample=0;startTime={minTime};'
                f'endTime={endTime};frameStride=1;frameSample=0.0;defaultUSDFormat=usdc;'
                f'parentScope=/{character_name};shadingMode=useRegistry;convertMaterialsTo=UsdPreviewSurface;'
                f'exportInstances=1;exportVisibility=1;mergeTransformAndShape=1;stripNamespaces=0'
            )

            import maya.mel as mel
            usd_path = local_file_path.replace("\\", "/")
            with suppress_stdout_stderr():
                mel.eval(f'catch(`file -force -options "{usd_options}" -typ "USD Export" -pr -es "{usd_path}"`);')

            # geo 정리
            if cmds.objExists("geo"):
                try:
                    cmds.delete("geo")
                except:
                    pass

            # 네트워크 복사/정리
            network_path = get_cache_dir_path(scene_number, cut_number)
            dst_path = os.path.normpath(os.path.join(network_path, file_name))
            os.makedirs(network_path, exist_ok=True)
            shutil.copy(local_file_path, dst_path)
            os.remove(local_file_path)

            success = True

        except Exception as e:
            cmds.warning(f"[ERROR] USD 익스포트 오류: {e}")
        finally:
            cmds.select(clear=True)
            toggle_viewport(True)

        return success


            
# def export_usd(character_name, character_group, scene_number, cut_number, minTime):
    # """
    # 캐릭터 그룹 하위의 'geo'만 복사해서 USD로 익스포트.
    # 이름은 항상 'geo'로 고정, headTip_skin 베이크 포함.
    # 실패해도 정리/복원 안전하게 처리됨.
    # """
    # with EvalModeGuard('off'):  # DG 모드 전환
        # toggle_viewport(False)

        # # ✅ headTip_skin 있으면 베이크
        # bake_cha(character_name)

        # # 💧 사전 정리
        # if cmds.objExists("geo") and cmds.nodeType("geo") == "transform":
            # try:
                # cmds.delete("geo")
            # except:
                # pass

        # if cmds.objExists("geo") and cmds.nodeType("geo") == "displayLayer":
            # try:
                # new_layer_name = "geo_displayLayer_old"
                # if cmds.objExists(new_layer_name):
                    # cmds.delete(new_layer_name)
                # cmds.rename("geo", new_layer_name)
            # except:
                # pass

        # # 🎯 geo 찾기 (has_geo_child 사용)
        # geo_node = has_geo_child(character_group)
        # if not geo_node:
            # cmds.warning(f"[ERROR] '{character_group}' 하위에 'geo' 그룹이 없습니다.")
            # toggle_viewport(True)
            # return False

        # # ✨ 복제 및 월드로 언패런트
        # try:
            # duplicated_geo = cmds.duplicate(geo_node, rr=True, ic=True)[0]
            # parent = cmds.listRelatives(duplicated_geo, parent=True, fullPath=True)
            # if parent:
                # cmds.parent(duplicated_geo, world=True)
        # except Exception as e:
            # cmds.warning(f"[ERROR] 복제 또는 언패런트 실패: {e}")
            # toggle_viewport(True)
            # return False

        # # 🏷️ 이름 고정
        # if duplicated_geo != "geo":
            # if cmds.objExists("geo"):
                # try:
                    # cmds.delete("geo")
                # except:
                    # pass
            # try:
                # duplicated_geo = cmds.rename(duplicated_geo, "geo")
            # except:
                # toggle_viewport(True)
                # return False

        # # 📦 USD 익스포트
        # success = False
        # try:
            # cmds.select("geo")
            # endTime = cmds.playbackOptions(q=True, max=True)
            # cmds.bakeResults("geo", t=(minTime, endTime), shape=True)

            # file_name = f"{get_project_prefix()}_{scene_number}_{cut_number}_ch_{character_name}.usd"
            # local_cache_path = os.path.normpath(os.path.join(os.getenv('TEMP'), 'MayaUSDExport'))
            # local_file_path = os.path.normpath(os.path.join(local_cache_path, file_name))
            # os.makedirs(local_cache_path, exist_ok=True)

            # usd_options = (
                # f';exportUVs=1;exportSkels=none;exportSkin=none;exportBlendShapes=0;'
                # f'exportDisplayColor=0;filterTypes=nurbsCurve;exportColorSets=0;'
                # f'defaultMeshScheme=none;animation=1;eulerFilter=0;staticSingleSample=0;startTime={minTime};'
                # f'endTime={endTime};frameStride=1;frameSample=0.0;defaultUSDFormat=usdc;'
                # f'parentScope=/{character_name};shadingMode=useRegistry;convertMaterialsTo=UsdPreviewSurface;'
                # f'exportInstances=1;exportVisibility=1;mergeTransformAndShape=1;stripNamespaces=0'
            # )

            # # ✅ catch 적용 (에러 무시) - 경로 따로 치환
            # import maya.mel as mel
            # usd_path = local_file_path.replace("\\", "/")
            # with suppress_stdout_stderr():
                # mel.eval(f'catch(`file -force -options "{usd_options}" -typ "USD Export" -pr -es "{usd_path}"`);')


            # if cmds.objExists("geo"):
                # try:
                    # cmds.delete("geo")
                # except:
                    # pass

            # network_path = os.path.normpath(os.path.join(get_project_paths(), "scenes", scene_number, cut_number, "ren", "cache"))
            # dst_path = os.path.normpath(os.path.join(network_path, file_name))
            # os.makedirs(network_path, exist_ok=True)
            # shutil.copy(local_file_path, dst_path)
            # os.remove(local_file_path)

            # success = True

        # except Exception as e:
            # cmds.warning(f"[ERROR] USD 익스포트 오류: {e}")

        # finally:
            # cmds.select(clear=True)
            # toggle_viewport(True)

        # return success

def export_usd_prop(scene_number, cut_number, prop_name, prop_group):
    """
    Prop 애님아웃 USD 익스포트
    - prop_name: UI에서 만든 unique_name (파일명, parentScope 용)
    - prop_group: Maya 씬 DAG 경로 (cmds.select 등 Maya 조작 용)
    """
    with EvalModeGuard('off'):
        toggle_viewport(False)

        # 기존 geo 삭제
        if cmds.objExists("geo") and cmds.nodeType("geo") == "transform":
            try:
                cmds.delete("geo")
            except:
                pass

        # ✅ prop_group 기준으로 geo 찾기
        geo_node = has_geo_child(prop_group)
        if not geo_node:
            cmds.warning(f"[ERROR] '{prop_group}' 하위에 'geo' 그룹이 없습니다.")
            toggle_viewport(True)
            return False

        try:
            # ✅ prop_group 기준 복제
            duplicated_geo = cmds.duplicate(geo_node, rr=True, ic=True)[0]
            parent = cmds.listRelatives(duplicated_geo, parent=True, fullPath=True)
            if parent:
                cmds.parent(duplicated_geo, world=True)
        except Exception as e:
            cmds.warning(f"[ERROR] 복제 실패: {e}")
            toggle_viewport(True)
            return False

        # 이름을 geo로 고정
        if duplicated_geo != "geo":
            if cmds.objExists("geo"):
                try:
                    cmds.delete("geo")
                except:
                    pass
            try:
                duplicated_geo = cmds.rename(duplicated_geo, "geo")
            except:
                pass

        try:
            # ✅ 선택은 geo 로
            cmds.select("geo")
            start_frame = int(cmds.playbackOptions(q=True, min=True))
            end_frame = int(cmds.playbackOptions(q=True, max=True))
            cmds.bakeResults("geo", t=(start_frame, end_frame), shape=True)

            # USD 임시 경로
            file_name = f"{get_project_prefix()}_{scene_number}_{cut_number}_prop_{prop_name}.usd"
            local_path = os.path.join(os.getenv('TEMP'), 'MayaUSDExport')
            os.makedirs(local_path, exist_ok=True)
            local_usd = os.path.join(local_path, file_name)

            # ✅ parentScope 에는 unique_name(prop_name) 사용
            usd_options = (
                f';exportUVs=1;exportSkels=none;exportSkin=none;exportBlendShapes=0;'
                f'exportDisplayColor=0;filterTypes=nurbsCurve;exportColorSets=0;'
                f'defaultMeshScheme=none;animation=1;eulerFilter=0;staticSingleSample=0;'
                f'startTime={start_frame};endTime={end_frame};frameStride=1;frameSample=0.0;'
                f'defaultUSDFormat=usdc;parentScope=/{prop_name};'
                f'shadingMode=useRegistry;convertMaterialsTo=UsdPreviewSurface;'
                f'exportInstances=1;exportVisibility=1;mergeTransformAndShape=1;stripNamespaces=0'
            )

            import maya.mel as mel
            usd_path = local_usd.replace("\\", "/")
            with suppress_stdout_stderr():
                mel.eval(f'catch(`file -force -options "{usd_options}" -typ "USD Export" -pr -es "{usd_path}"`);')

            # 네트워크 캐시에 복사
            network_path = get_cache_dir_path(scene_number, cut_number)
            os.makedirs(network_path, exist_ok=True)
            dst_usd = os.path.join(network_path, file_name)
            shutil.copy(local_usd, dst_usd)
            os.remove(local_usd)

            print(f"✅ USD 저장 완료: {dst_usd}")

            # JSON 저장
            json_file = dst_usd.replace(".usd", ".json")
            export_meta = {
                "scene": scene_number,
                "cut": cut_number,
                "prop": prop_name,
                "usd": dst_usd,
                "frames": [start_frame, end_frame]
            }
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(export_meta, f, indent=4, ensure_ascii=False)

            print(f"🧾 JSON 저장 완료: {json_file}")

        except Exception as e:
            cmds.warning(f"[ERROR] USD 익스포트 오류: {e}")
            toggle_viewport(True)
            return False

        finally:
            if cmds.objExists("geo"):
                try:
                    cmds.delete("geo")
                except:
                    pass
            cmds.select(clear=True)
            toggle_viewport(True)
            refresh_animout_ui('prop')

        return True



def export_usd_bg(bg_name, bg_geo, scene_number, cut_number, selected_only=False):
    """
    BG 애님아웃을 캐릭터 익스포트 방식과 동일하게 수정:
    - 지오메트리 복제 및 'geo' 이름 고정
    - bakeResults를 통한 애니메이션 베이크 수행
    - USD 익스포트 및 네트워크 경로 복사
    """
    with EvalModeGuard('off'):  # DG 모드 전환
        toggle_viewport(False)

        # 1. 기존 'geo' 노드 및 레이어 정리 (캐릭터와 동일한 cleanup)
        if cmds.objExists("geo") and cmds.nodeType("geo") == "transform":
            try:
                cmds.delete("geo")
            except:
                pass

        if cmds.objExists("geo") and cmds.nodeType("geo") == "displayLayer":
            try:
                new_layer_name = "geo_displayLayer_old"
                if cmds.objExists(new_layer_name):
                    cmds.delete(new_layer_name)
                cmds.rename("geo", new_layer_name)
            except:
                pass

        # 2. 대상 BG 확보
        if selected_only:
            # UI에서 선택된 BG들
            targets = list(selected_bg_names)
        else:
            # animSet에 등록된 BG들
            anim_set = "animSet"
            targets = cmds.sets(anim_set, q=True) if cmds.objExists(anim_set) else []

        if not targets:
            toggle_viewport(True)
            return False

        success = True
        minTime = int(cmds.playbackOptions(q=True, min=True))
        endTime = int(cmds.playbackOptions(q=True, max=True))
        project_prefix = get_project_prefix()

        for obj in targets:
            if not cmds.objExists(obj):
                continue

            # 🎯 geo 찾기 (has_geo_child 사용)
            geo_node = has_geo_child(obj)
            if not geo_node:
                cmds.warning(f"[Skip] '{obj}' 하위에 'geo' 그룹이 없어 건너뜜.")
                continue

            short_name = obj.split("|")[-1].split(":")[-1]
            
            try:
                # ✨ 복제 및 월드로 언패런트
                duplicated_geo = cmds.duplicate(geo_node, rr=True, ic=True)[0]
                parent = cmds.listRelatives(duplicated_geo, parent=True, fullPath=True)
                if parent:
                    cmds.parent(duplicated_geo, world=True)
                
                # 🏷️ 이름 'geo'로 고정
                if duplicated_geo != "geo":
                    if cmds.objExists("geo"):
                        try: cmds.delete("geo")
                        except: pass
                    duplicated_geo = cmds.rename(duplicated_geo, "geo")

                # ✅ 캐릭터와 동일한 베이크 시퀀스 (bakeResults)
                cmds.select("geo", r=True)
                cmds.bakeResults("geo", t=(minTime, endTime), shape=True)

                # 파일명 및 경로 설정
                file_name = f"{project_prefix}_{scene_number}_{cut_number}_bg_{short_name}.usd"
                local_cache_path = os.path.normpath(os.path.join(os.getenv('TEMP'), 'MayaUSDExport'))
                os.makedirs(local_cache_path, exist_ok=True)
                local_file_path = os.path.normpath(os.path.join(local_cache_path, file_name))

                # USD 익스포트 옵션
                usd_options = (
                    f';exportUVs=1;exportSkels=none;exportSkin=none;exportBlendShapes=0;'
                    f'exportDisplayColor=0;filterTypes=nurbsCurve;exportColorSets=0;'
                    f'defaultMeshScheme=none;animation=1;eulerFilter=0;staticSingleSample=0;startTime={minTime};'
                    f'endTime={endTime};frameStride=1;frameSample=0.0;defaultUSDFormat=usdc;'
                    f'parentScope=/{short_name};shadingMode=useRegistry;convertMaterialsTo=UsdPreviewSurface;'
                    f'exportInstances=1;exportVisibility=1;mergeTransformAndShape=1;stripNamespaces=0'
                )

                import maya.mel as mel
                usd_path = local_file_path.replace("\\", "/")
                with suppress_stdout_stderr():
                    mel.eval(f'catch(`file -force -options "{usd_options}" -typ "USD Export" -pr -es "{usd_path}"`);')

                # 정리 및 네트워크 복사
                if cmds.objExists("geo"):
                    cmds.delete("geo")

                network_path = get_cache_dir_path(scene_number, cut_number)
                os.makedirs(network_path, exist_ok=True)
                dst_path = os.path.normpath(os.path.join(network_path, file_name))
                shutil.copy(local_file_path, dst_path)
                os.remove(local_file_path)

                print(f"✅ BG 익스포트 성공: {short_name}")

            except Exception as e:
                cmds.warning(f"[ERROR] BG 익스포트 오류 ({short_name}): {e}")
                success = False

        refresh_animout_ui('bg')
        cmds.select(clear=True)
        toggle_viewport(True)
        return success

# def export_usd_bg(bg_name, bg_geo, scene_number, cut_number, selected_only=False):
    # with EvalModeGuard('off'):
        # set_name = "animSet"

        # if selected_only:
            # members = list(selected_bg_names)
        # else:
            # if not cmds.objExists(set_name):
                # cmds.warning(f"⚠️ '{set_name}'이 존재하지 않습니다.")
                # return False
            # members = cmds.sets(set_name, q=True) or []

        # if not members:
            # return False

        # base_path = get_project_paths()
        # project_prefix = get_project_prefix()
        # cache_dir = os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache")
        # if not os.path.exists(cache_dir):
            # os.makedirs(cache_dir)

        # start_frame = int(cmds.playbackOptions(q=True, min=True))
        # end_frame = int(cmds.playbackOptions(q=True, max=True))

        # toggle_viewport(False)
        # for obj in members:
            # if not cmds.objExists(obj):
                # continue

            # short_name = obj.split("|")[-1].split(":")[-1]
            # obj_data = {"translate": {}, "rotate": {}, "scale": {}, "startFrame": start_frame, "endFrame": end_frame}

            # for frame in range(start_frame, end_frame + 1):
                # cmds.currentTime(frame)
                # t = [cmds.getAttr(f"{obj}.translate{axis}") for axis in "XYZ"]
                # r = [cmds.getAttr(f"{obj}.rotate{axis}") for axis in "XYZ"]
                # s = [cmds.getAttr(f"{obj}.scale{axis}") for axis in "XYZ"]
                # obj_data["translate"][str(frame)] = t
                # obj_data["rotate"][str(frame)] = r
                # obj_data["scale"][str(frame)] = s

            # file_name = f"{project_prefix}_{scene_number}_{cut_number}_anim_{short_name}.json"
            # json_path = os.path.join(cache_dir, file_name)
            # try:
                # with open(json_path, "w") as f:
                    # json.dump(obj_data, f, indent=4)
                # print(f"✅ {short_name} 저장 완료: {json_path}")
            # except Exception as e:
                # cmds.warning(f"🚨 저장 실패 ({short_name}): {e}")

        # refresh_animout_ui('bg')
        # toggle_viewport(True)
        # return True

def get_selected_camera_from_scene():
    selected = cmds.ls(selection=True, long=True) or []
    for obj in selected:
        shapes = cmds.listRelatives(obj, shapes=True, fullPath=True) or []
        for shape in shapes:
            if cmds.nodeType(shape) == 'camera':
                return obj  # transform 이름 리턴
    return None

def export_selected_camera_from_scene(*args):
    cam = get_selected_camera_from_scene()
    if not cam:
        cmds.warning("선택된 카메라가 없습니다.")
        return
    scene_number, cut_number = get_scene_and_cut()
    selected_cam_names.clear()
    selected_cam_names.add(cam)
    export_camera(scene_number, cut_number, selected_only=True)


# def export_camera(scene_number, cut_number, selected_only=False):
    # with EvalModeGuard('off'):
        # toggle_viewport(False)
        # if selected_only:
            # cameras = list(selected_cam_names)
        # else:
            # cam = get_scene_cut_camera()
            # cameras = [cam] if cam else []

        # if not cameras:
            # cmds.warning("No valid camera found to export.")
            # return

        # for original_camera_name in cameras:
            # if not cmds.objExists(original_camera_name):
                # continue

            # cmds.camera(original_camera_name, edit=True, lockTransform=False)
            # project_prefix = get_project_prefix()
            # duplicated_camera = cmds.duplicate(original_camera_name, rr=True, ic=True, name=f"{project_prefix}_{original_camera_name}")[0]
            # cmds.xform(duplicated_camera, centerPivots=True)   # 🔥 추가: 센터 피벗
            # cmds.parentConstraint(original_camera_name, duplicated_camera, mo=True)
            # cmds.parent(duplicated_camera, world=True)
            # cmds.bakeResults(duplicated_camera, t=(cmds.playbackOptions(q=True, minTime=True),
                                                   # cmds.playbackOptions(q=True, maxTime=True)))

            # base_path = get_project_paths()
            # export_path = os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache")
            # if not os.path.exists(export_path):
                # os.makedirs(export_path)

            # json_file_name = f"{project_prefix}_{scene_number}_{cut_number}_camera_data.json"
            # full_json_path = os.path.join(export_path, json_file_name)
            # resolution_width = cmds.getAttr("defaultResolution.width")
            # resolution_height = cmds.getAttr("defaultResolution.height")
            # min_time = cmds.playbackOptions(q=True, minTime=True)
            # max_time = cmds.playbackOptions(q=True, maxTime=True)
            # camera_data = {"resolutionX": resolution_width, "resolutionY": resolution_height, "minTime": min_time, "maxTime": max_time}
            # with open(full_json_path, 'w') as json_file:
                # json.dump(camera_data, json_file, indent=4)
            # print(f"Camera data exported to {full_json_path}")

            # file_name = f"{project_prefix}_{scene_number}_{cut_number}_cam.fbx"
            # full_export_path = os.path.join(export_path, file_name)
            # cmds.select(duplicated_camera)
            # cmds.file(full_export_path, force=True, options="v=0;cameras=1;bakeAnimations=1", type="FBX export", pr=True, es=True)
            # cmds.delete(duplicated_camera)
            # print(f"Camera exported successfully to {full_export_path}.")
        # refresh_animout_ui('cam')
        
def safe_parent_to_world(obj):
    """부모가 있으면 world로 언패런트, 이미 world면 로그만 찍고 종료."""
    try:
        parent = cmds.listRelatives(obj, parent=True, fullPath=True)
        if not parent:
            print(f"[AnimOut] already world parent: {obj}")
            return

        cmds.parent(obj, world=True)
        print(f"[AnimOut] parented to world: {obj}")

    except Exception as e:
        print(f"[AnimOut][WARN] parent world 실패: {obj} -> {e}")

def _get_vector_attr(node, attr):
    """compound vector attr 안전 조회."""
    try:
        value = cmds.getAttr(f"{node}.{attr}")
        if isinstance(value, list) or isinstance(value, tuple):
            if value and isinstance(value[0], (list, tuple)):
                return list(value[0])
            return list(value)
    except:
        pass
    return [0.0, 0.0, 0.0]


def is_transform_pivot_dirty(node, tolerance=0.0001):
    """
    아티스트가 Insert pivot 등으로 pivot을 움직였는지 검사.
    rotatePivot / scalePivot / pivotTranslate 계열만 본다.
    """
    values = []
    values += _get_vector_attr(node, "rotatePivot")
    values += _get_vector_attr(node, "scalePivot")
    values += _get_vector_attr(node, "rotatePivotTranslate")
    values += _get_vector_attr(node, "scalePivotTranslate")

    return any(abs(v) > tolerance for v in values)


def cleanup_camera_pivot_for_export(camera_transform, tolerance=0.0001):
    """
    카메라 export용 사본에만 적용.
    centerPivots가 아니라 zeroTransformPivots 사용.
    """
    if not cmds.objExists(camera_transform):
        return

    if is_transform_pivot_dirty(camera_transform, tolerance=tolerance):
        print(f"[AnimOut] Camera pivot offset detected: {camera_transform}")
        cmds.xform(camera_transform, zeroTransformPivots=True)
        print(f"[AnimOut] zeroTransformPivots applied: {camera_transform}")
    else:
        print(f"[AnimOut] Camera pivot clean: {camera_transform}")


def export_camera(scene_number, cut_number, selected_only=False):
    with EvalModeGuard('off'):
        toggle_viewport(False)

        if selected_only:
            cameras = list(selected_cam_names)
        else:
            cam = get_scene_cut_camera()
            cameras = [cam] if cam else []

        if not cameras:
            cmds.warning("No valid camera found to export.")
            toggle_viewport(True)
            return False

        for original_camera_name in cameras:
            if not cmds.objExists(original_camera_name):
                continue

            # 1. 원본 카메라 transform lock 해제
            #    duplicate 제한 회피 목적. 원본 씬은 저장하지 않으므로 복구하지 않음.
            cmds.camera(original_camera_name, edit=True, lockTransform=False)

            project_prefix = get_project_prefix()

            # 2. 원본 복제
            duplicated_camera = cmds.duplicate(
                original_camera_name,
                rr=True,
                ic=True,
                name=f"{project_prefix}_{original_camera_name}"
            )[0]

            # 3. 사본을 world로 분리
            safe_parent_to_world(duplicated_camera)

            # 4. 사본 카메라의 pivot offset만 정리
            #    centerPivots 금지. 카메라 bbox 중심으로 가면 Blender에서 더 틀어질 수 있음.
            cleanup_camera_pivot_for_export(duplicated_camera)

            # 5. 사본 transform 초기화 후, 원본에 mo=False로 정확히 붙임
            try:
                cmds.setAttr(f"{duplicated_camera}.translate", 0, 0, 0)
                cmds.setAttr(f"{duplicated_camera}.rotate", 0, 0, 0)
                cmds.setAttr(f"{duplicated_camera}.scale", 1, 1, 1)
            except Exception as e:
                print(f"[AnimOut][WARN] duplicate transform 초기화 실패: {duplicated_camera} -> {e}")

            temp_constraint = cmds.parentConstraint(
                original_camera_name,
                duplicated_camera,
                mo=False
            )

            # 6. 베이크
            min_time = cmds.playbackOptions(q=True, minTime=True)
            max_time = cmds.playbackOptions(q=True, maxTime=True)

            cmds.bakeResults(
                duplicated_camera,
                t=(min_time, max_time),
                simulation=True,
                sampleBy=1,
                oversamplingRate=1,
                disableImplicitControl=True,
                preserveOutsideKeys=True,
                sparseAnimCurveBake=False,
                minimizeRotation=True,
                controlPoints=False,
                shape=True
            )

            # 7. constraint 삭제
            try:
                if temp_constraint and cmds.objExists(temp_constraint[0]):
                    cmds.delete(temp_constraint[0])
            except:
                pass

            # 8. export path
            base_path = get_project_paths()
            export_path = os.path.join(
                base_path,
                "scenes",
                scene_number,
                cut_number,
                "ren",
                "cache"
            )
            if not os.path.exists(export_path):
                os.makedirs(export_path)

            # 9. 카메라 속성 JSON
            cam_shape = cmds.listRelatives(original_camera_name, shapes=True, fullPath=True)
            if cam_shape:
                cam_shape = cam_shape[0]
                focal_length = cmds.getAttr(f"{cam_shape}.focalLength")
                h_aperture_inch = cmds.getAttr(f"{cam_shape}.horizontalFilmAperture")
                v_aperture_inch = cmds.getAttr(f"{cam_shape}.verticalFilmAperture")
                h_aperture_mm = round(h_aperture_inch * 25.4, 3)
                v_aperture_mm = round(v_aperture_inch * 25.4, 3)
            else:
                focal_length = 0.0
                h_aperture_mm = 0.0
                v_aperture_mm = 0.0

            json_file_name = f"{project_prefix}_{scene_number}_{cut_number}_camera_data.json"
            full_json_path = os.path.join(export_path, json_file_name)

            camera_data = {
                "resolutionX": cmds.getAttr("defaultResolution.width"),
                "resolutionY": cmds.getAttr("defaultResolution.height"),
                "minTime": min_time,
                "maxTime": max_time,
                "focalLength": focal_length,
                "horizontalAperture_mm": h_aperture_mm,
                "verticalAperture_mm": v_aperture_mm
            }

            with open(full_json_path, "w") as json_file:
                json.dump(camera_data, json_file, indent=4)

            print(f"Camera data exported to {full_json_path}")

            # 10. FBX Export
            file_name = f"{project_prefix}_{scene_number}_{cut_number}_cam.fbx"
            full_export_path = os.path.join(export_path, file_name)

            cmds.select(duplicated_camera, r=True)
            cmds.file(
                full_export_path,
                force=True,
                options="v=0;cameras=1;bakeAnimations=1",
                type="FBX export",
                pr=True,
                es=True
            )

            cmds.delete(duplicated_camera)
            print(f"Camera exported successfully to {full_export_path}.")

        refresh_animout_ui('cam')
        toggle_viewport(True)
        return True
    
def export_all():
    export_all_characters()
    export_all_props()
    export_usd_bg(None, None, *get_scene_and_cut(), selected_only=False)
    export_camera(*get_scene_and_cut())

def export_Selected():
    scene_number, cut_number = get_scene_and_cut()
    min_time = int(cmds.optionMenu('minTimeMenu', query=True, value=True))

    # ✅ 복사본을 기준으로 순회
    for group_path in list(selected_character_names):
        short_name = group_path.split('|')[-1].split(':')[-1]
        export_usd(short_name, group_path, scene_number, cut_number, min_time)

    for group_path in list(selected_prop_names):
        short_name = group_path.split('|')[-1].split(':')[-1]
        export_usd_prop(scene_number, cut_number, short_name, group_path)

    export_usd_bg(None, None, scene_number, cut_number, selected_only=True)

    for group_path in list(selected_cam_names):
        export_camera(scene_number, cut_number)

# ✅ 항상 보이는 상단 버튼 (frameLayout 아래에 위치)
def select_all_items(part):
    name_map = {
        'ch': (character_button_refs, selected_character_names, 'ch'),
        'prop': (prop_button_refs, selected_prop_names, 'prop'),
        'bg': (bg_button_refs, selected_bg_names, 'bg'),
        'cam': (cam_button_refs, selected_cam_names, 'cam')
    }
    if part not in name_map:
        return

    button_refs, selected_names, category = name_map[part]

    # 토글 방식: 전부 선택 or 전체 해제
    if len(selected_names) < len(button_refs):
        selected_names.clear()
        selected_names.update(button_refs.keys())

        if category == "prop":
            selected_prop_paths.clear()
            for unique_name, data in button_refs.items():
                group_path = data[1] if isinstance(data, tuple) else data
                selected_prop_paths[unique_name] = group_path

        if category == "ch":
            selected_character_paths.clear()
            for unique_name, data in button_refs.items():
                group_path = data[1] if isinstance(data, tuple) else data
                selected_character_paths[unique_name] = group_path
    else:
        selected_names.clear()
        if category == "prop":
            selected_prop_paths.clear()
        if category == "ch":
            selected_character_paths.clear()

    cmds.select(clear=True)
    for obj in selected_names:
        if not cmds.objExists(obj):
            continue
        geo_path = find_geo_path(obj) if category != 'bg' else obj
        if cmds.objExists(geo_path):
            cmds.select(geo_path, add=True)

    update_item_button_styles(button_refs, selected_names, category, *get_scene_and_cut())



def export_selected_items(part):
    scene_number, cut_number = get_scene_and_cut()
    min_time = int(cmds.optionMenu('minTimeMenu', query=True, value=True))

    success = True

    if part == 'ch':
        items = selected_character_paths if selected_character_paths else find_characters_in_scene()
        for unique_name, group_path in items.items():
            if not group_path:
                continue
            try:
                result = export_usd(unique_name, group_path, scene_number, cut_number, min_time)
                if not result:
                    success = False
            except Exception as e:
                print(f"❌ 캐릭터 익스포트 실패: {unique_name} → {e}")
                success = False


    elif part == 'prop':
        items = selected_prop_paths if selected_prop_paths else find_props_in_scene()
        for unique_name, group_path in items.items():
            try:
                result = export_usd_prop(scene_number, cut_number, unique_name, group_path)
                if not result:
                    success = False
            except Exception as e:
                print(f"❌ 프랍 익스포트 실패: {unique_name} → {e}")
                success = False

    elif part == 'bg':
        items = find_bgs_in_scene()
        target_names = selected_bg_names if selected_bg_names else items.keys()
        for unique_name in target_names:
            group_path = items.get(unique_name)
            if not group_path:
                continue
            try:
                result = export_usd_bg(unique_name, group_path, scene_number, cut_number, selected_only=True)
                if not result:
                    success = False
            except Exception as e:
                print(f"❌ BG 익스포트 실패: {unique_name} → {e}")
                success = False

    elif part == 'cam':
        cam = get_scene_cut_camera()
        if cam:
            try:
                result = export_camera(scene_number, cut_number)
                if not result:
                    success = False
            except Exception as e:
                print(f"❌ 카메라 익스포트 실패: {cam} → {e}")
                success = False

    refresh_animout_ui(part)

    if success:
        print(f"✅ {part.upper()} 애님아웃 완료")
    else:
        print(f"❌ 일부 {part.upper()} 애님아웃 실패")




def update_category_menu(*args):
    clear_option_menu_items(categoryMenuName)
    categories = sorted(asset_cache["categories"])
    for category in categories:
        cmds.menuItem(parent=categoryMenuName, label=category)
    update_asset_menu()
    
def update_project_settings(project):
    global current_project
    current_project = project
    print(f"Project updated to: {current_project}")

def updateUI():
    current_project = get_current_project()
    set_current_project(current_project)
    cmds.optionMenu(projectMenuName, edit=True, value=current_project)
    update_scenes()
    scene, cut = get_scene_and_cut()
    camera = get_scene_cut_camera()
    found_bgs = find_bgs_in_scene()

def refresh_ui_on_new_file():
    global scriptJobId
    if scriptJobId is not None and cmds.scriptJob(exists=scriptJobId):
        cmds.scriptJob(kill=scriptJobId, force=True)
    if cmds.window("rrAnimout", exists=True):
        scriptJobId = cmds.scriptJob(e=["SceneOpened", on_file_opened_callback], protected=True)

def on_file_opened_callback(*args):
    """씬 열릴 때 실행되는 콜백"""
    if cmds.window("rrAnimout", exists=True):
        cmds.deleteUI("rrAnimout")
    # 씬/컷 번호 가져오기
    scene, cut = get_scene_and_cut()
    update_camera_name(scene, cut)   # ✅ 씬 열릴 때 카메라 이름 검사
        
def update_camera_name(scene_number, cut_number):
    camera = get_scene_cut_camera()
    if not camera:
        return None
    expected_camera_name = f"cam_{scene_number}_{cut_number}"
    if camera and camera != expected_camera_name:
        result = cmds.confirmDialog(
            title='카메라 이름 수정',
            message=f"카메라 이름이 파일 이름과 일치하지 않습니다. 수정할까요?\n기존 이름: {camera}\n새 이름: {expected_camera_name}",
            button=['OK', 'Cancel'],
            defaultButton='OK',
            cancelButton='Cancel'
        )
        if result == 'OK':
            cmds.rename(camera, expected_camera_name)
            return expected_camera_name
    return camera
    
def export_avatar():
    # 현재 열려있는 마야 파일 이름 가져오기
    current_file = cmds.file(query=True, sceneName=True, shortName=True)
    if not current_file:
        cmds.error("저장된 마야 파일이 없습니다. 먼저 파일을 저장하세요.")
        return
    
    # 파일 이름에서 프로젝트 접두사, 씬 번호, 컷 번호 추출
    file_name_parts = os.path.splitext(current_file)[0].split("_")
    if len(file_name_parts) < 3:
        cmds.error(f"파일 이름 형식이 잘못되었습니다: {current_file}")
        return
    
    base_path = get_project_paths()
    scene_number = file_name_parts[1]
    cut_number = file_name_parts[2]
    project_prefix = get_project_prefix()
    cfx_start_frame = int(cmds.optionMenu('minTimeMenu', query=True, value=True))
    cmds.currentTime(cfx_start_frame, edit=True)
    minTime = cfx_start_frame
    maxTime = cmds.playbackOptions(query=True, maxTime=True)
    
    # 경로 생성
    export_path = os.path.join(base_path, f"/scenes/{scene_number}/{cut_number}/ren/cache/")
    os.makedirs(export_path, exist_ok=True)

    # 선택된 오브젝트 가져오기
    selected_objects = cmds.ls(selection=True)
    if not selected_objects:
        cmds.error("선택된 오브젝트가 없습니다.")
        return

    # 네임스페이스 제거 후 첫 번째 오브젝트 이름 추출
    first_object_name = selected_objects[0].split(":")[-1]

    # 파일 이름 생성
    export_file = f"{project_prefix}_{scene_number}_{cut_number}_avatar_{first_object_name}.abc"
    full_path = os.path.join(export_path, export_file)

    # 알렘빅 익스포트 명령 생성
    abc_command = f"-frameRange {minTime} {maxTime} "
    abc_command += "-uvWrite -worldSpace -writeVisibility "
    abc_command += "-dataFormat ogawa "
    abc_command += " ".join([f"-root |{cmds.ls(obj, long=True)[0]}" for obj in selected_objects])
    abc_command += f" -file \"{full_path}\""

    # 알렘빅 익스포트 실행
    try:
        cmds.AbcExport(j=abc_command)
        print(f"알렘빅 파일이 성공적으로 저장되었습니다: {full_path}")
    except Exception as e:
        cmds.error(f"알렘빅 익스포트 중 오류 발생: {e}")


def export_garment():
    """선택한 각 오브젝트를 개별 Garment OBJ로 익스포트 (CFX Start Frame에서)."""
    current_file = cmds.file(query=True, sceneName=True, shortName=True)
    if not current_file:
        cmds.error("저장된 마야 파일이 없습니다. 먼저 파일을 저장하세요.")
        return

    file_name_parts = os.path.splitext(current_file)[0].split("_")
    if len(file_name_parts) < 3:
        cmds.error(f"파일 이름 형식이 잘못되었습니다: {current_file}")
        return

    base_path = get_project_paths()
    scene_number = file_name_parts[1]
    cut_number = file_name_parts[2]
    project_prefix = get_project_prefix()

    # CFX Start Frame으로 시점 이동
    cfx_start_frame = int(cmds.optionMenu('minTimeMenu', query=True, value=True))
    cmds.currentTime(cfx_start_frame, edit=True)

    # 선택된 트랜스폼만 대상
    selected_objects = cmds.ls(selection=True, type='transform')
    if not selected_objects:
        cmds.error("선택된 오브젝트가 없습니다.")
        return

    export_path = os.path.join(base_path, f"scenes/{scene_number}/{cut_number}/ren/cache/")
    os.makedirs(export_path, exist_ok=True)

    # 개별 익스포트
    for obj in selected_objects:
        # 롱패스 확보
        long_list = cmds.ls(obj, long=True)
        if not long_list:
            cmds.warning(f"대상 찾을 수 없음: {obj}")
            continue
        long_obj = long_list[0]

        # 파일명: 네임스페이스 제거
        short_name = obj.split(":")[-1]
        # 파일 경로
        export_file = f"{project_prefix}_{scene_number}_{cut_number}_garment_{short_name}.obj"
        full_path = os.path.join(export_path, export_file)

        try:
            # 해당 오브젝트만 선택해서 익스포트
            cmds.select(long_obj, r=True)
            cmds.file(
                full_path,
                force=True,
                options="groups=1;ptgroups=1;materials=0;smoothing=1;normals=1",
                typ="OBJexport",
                pr=True,
                es=True  # Export Selected
            )
            print(f"✅ Garment OBJ 저장: {full_path}")
        except Exception as e:
            cmds.warning(f"❌ Garment OBJ 익스포트 실패 ({short_name}): {e}")

    # 선택 해제
    cmds.select(clear=True)



def get_or_create_anim_set():
    if not cmds.objExists("animSet"):
        cmds.sets(name="animSet", empty=True)
    return "animSet"

def add_selected_to_anim_set(*args):
    anim_set = get_or_create_anim_set()
    selected = cmds.ls(selection=True, long=True)
    if selected:
        cmds.sets(selected, add=anim_set)
    refresh_animout_ui('bg')

def remove_selected_from_anim_set(*args):
    if not cmds.objExists("animSet"):
        return
    selected = cmds.ls(selection=True, long=True)
    for obj in selected:
        if cmds.sets(obj, isMember="animSet"):
            cmds.sets(obj, remove="animSet")
    refresh_animout_ui('bg')


bg_button_refs = {}
selected_bg_names = set()
def shorten_name_for_button(name, max_length=7):
    """버튼용 이름 축약: 앞 5글자 + .. + 마지막 1글자"""
    if len(name) <= max_length:
        return name
    return name[:7]

def split_name_to_two_lines(name, max_per_line=7):
    """버튼 내 줄바꿈: 앞 7글자, 그 뒤 나머지"""
    if len(name) <= max_per_line:
        return name
    return name[:max_per_line] + "\n" + name[max_per_line:max_per_line * 2]


# ---------- 공통 UI 설정 ----------
BUTTON_WIDTH = 68
BUTTON_HEIGHT = 35
PROPS_PER_ROW = 4


def update_item_button_styles(button_refs, selected_names, category, scene_number, cut_number):
    for name, data in button_refs.items():
        # data가 tuple일 수 있음
        if isinstance(data, tuple):
            btn, group_path = data
        else:
            btn = data

        if not cmds.button(btn, exists=True):
            continue

        short_name = name.split(":")[-1]
        has_cache, export_time = get_export_status(short_name, category, scene_number, cut_number)
        base_color = [0.33, 0.43, 0.33] if has_cache else [0.43, 0.33, 0.33]
        color = [0.3, 0.6, 1.0] if name in selected_names else base_color
        label = f"{short_name}\n{export_time}" if has_cache else f"{short_name}\nNo Cache"
        cmds.button(btn, edit=True, backgroundColor=color, label=label)



def handle_item_click(unique_name, button_refs, selected_names, category, scene_number, cut_number):
    """
    버튼 클릭 시 선택 토글
    - selected_names: set (UI 선택 상태)
    - category == 'ch' 또는 'prop'일 경우, dict도 함께 업데이트
    """
    modifiers = cmds.getModifiers()
    shift = modifiers & 1
    ctrl = modifiers & 4
    all_keys = list(button_refs.keys())

    if shift and selected_names:
        last_selected = list(selected_names)[-1]
        try:
            start_index = all_keys.index(last_selected)
            end_index = all_keys.index(unique_name)
            if start_index > end_index:
                start_index, end_index = end_index, start_index
            range_selection = all_keys[start_index:end_index + 1]
            selected_names.clear()
            selected_names.update(range_selection)
        except ValueError:
            selected_names.clear()
            selected_names.add(unique_name)
    elif ctrl:
        if unique_name in selected_names:
            selected_names.remove(unique_name)
            if category == "prop" and unique_name in selected_prop_paths:
                del selected_prop_paths[unique_name]
            if category == "ch" and unique_name in selected_character_paths:
                del selected_character_paths[unique_name]
        else:
            selected_names.add(unique_name)
            data = button_refs.get(unique_name)
            group_path = data[1] if isinstance(data, tuple) else data
            if category == "prop":
                selected_prop_paths[unique_name] = group_path
            if category == "ch":
                selected_character_paths[unique_name] = group_path
    else:
        if len(selected_names) == 1 and unique_name in selected_names:
            selected_names.clear()
            if category == "prop":
                selected_prop_paths.clear()
            if category == "ch":
                selected_character_paths.clear()
        elif unique_name in selected_names:
            selected_names.clear()
            selected_names.add(unique_name)
            data = button_refs.get(unique_name)
            group_path = data[1] if isinstance(data, tuple) else data
            if category == "prop":
                selected_prop_paths.clear()
                selected_prop_paths[unique_name] = group_path
            if category == "ch":
                selected_character_paths.clear()
                selected_character_paths[unique_name] = group_path
        else:
            selected_names.clear()
            selected_names.add(unique_name)
            data = button_refs.get(unique_name)
            group_path = data[1] if isinstance(data, tuple) else data
            if category == "prop":
                selected_prop_paths.clear()
                selected_prop_paths[unique_name] = group_path
            if category == "ch":
                selected_character_paths.clear()
                selected_character_paths[unique_name] = group_path

    update_item_button_styles(button_refs, selected_names, category, scene_number, cut_number)


    
# 전역 버튼 저장소 및 선택 상태 저장소 선언
bg_button_refs = {}
character_button_refs = {}
prop_button_refs = {}
cam_button_refs = {}
selected_bg_names = set()
selected_character_names = set()         # UI 선택 상태
selected_character_paths = {}            # unique_name → group_path
selected_prop_names = set()       # 기존처럼 UI 선택 상태
selected_prop_paths = {}          # unique_name → group_path 매핑
selected_cam_names = set()

def setup_camera_ui(scene_number, cut_number):
    global cam_button_refs, selected_cam_names
    cam_button_refs.clear()
    selected_cam_names.clear()

    camera_name = get_scene_cut_camera()
    if not camera_name:
        # cmds.warning("No suitable camera found in the scene.")
        return

    camera_layout = cmds.columnLayout(adjustableColumn=True)
    row = cmds.rowLayout(
        numberOfColumns=PROPS_PER_ROW,
        columnWidth=[(j + 1, BUTTON_WIDTH) for j in range(PROPS_PER_ROW)],
        columnAlign=[(j + 1, 'center') for j in range(PROPS_PER_ROW)],
        columnAttach=[(j + 1, 'both', 0) for j in range(PROPS_PER_ROW)],
        parent=camera_layout
    )

    short_name = shorten_name_for_button(camera_name.split(":")[-1])
    short_name_wrapped = split_name_to_two_lines(short_name)

    # 캐시 상태 확인 (category는 'cam')
    has_cache, export_time = get_export_status(short_name, 'cam', scene_number, cut_number)
    label = f"{short_name_wrapped}\n{export_time}" if has_cache else f"{short_name_wrapped}\nNo Cache"
    color = [0.3, 0.6, 1.0] if camera_name in selected_cam_names else ([0.33, 0.43, 0.33] if has_cache else [0.43, 0.33, 0.33])

    btn = cmds.button(
        label=label,
        width=BUTTON_WIDTH,
        height=BUTTON_HEIGHT,
        backgroundColor=color,
        command=lambda *args: handle_item_click(
            camera_name, cam_button_refs, selected_cam_names, 'cam', scene_number, cut_number
        ),
        parent=row
    )
    cam_button_refs[camera_name] = btn

    update_item_button_styles(cam_button_refs, selected_cam_names, 'cam', scene_number, cut_number)
    cmds.setParent('..')
    cmds.setParent('..')



def setup_character_ui(found_characters, scene_number, cut_number):
    global character_button_refs, selected_character_names
    character_button_refs.clear()
    selected_character_names.clear()

    character_names = list(found_characters.keys())
    character_layout = cmds.columnLayout(adjustableColumn=True, co=('both', 0), rs=0, backgroundColor=[0.3, 0.33, 0.33])

    for i in range(0, len(character_names), PROPS_PER_ROW):
        row = cmds.rowLayout(
            numberOfColumns=PROPS_PER_ROW,
            columnWidth=[(j + 1, BUTTON_WIDTH) for j in range(PROPS_PER_ROW)],
            columnAlign=[(j + 1, 'center') for j in range(PROPS_PER_ROW)],
            columnAttach=[(j + 1, 'both', 0) for j in range(PROPS_PER_ROW)],
            parent=character_layout
        )

        for j in range(PROPS_PER_ROW):
            if i + j < len(character_names):
                unique_name = character_names[i + j]
                group_path = found_characters[unique_name]

                short_name_wrapped = split_name_to_two_lines(unique_name)
                has_cache, export_time = get_export_status(unique_name, 'ch', scene_number, cut_number)
                label = f"{short_name_wrapped}\n{export_time}" if has_cache else f"{short_name_wrapped}\nNo Cache"
                color = [0.3, 0.6, 1.0] if unique_name in selected_character_names else ([0.33, 0.43, 0.33] if has_cache else [0.43, 0.33, 0.33])

                btn = cmds.button(
                    label=label,
                    width=BUTTON_WIDTH,
                    height=BUTTON_HEIGHT,
                    backgroundColor=color,
                    command=lambda x, n=unique_name: handle_item_click(
                        n, character_button_refs, selected_character_names, 'ch', scene_number, cut_number
                    ),
                    parent=row
                )

                # ✅ unique_name을 키로 쓰고 group_path도 같이 저장
                character_button_refs[unique_name] = (btn, group_path)

        cmds.setParent('..')

    update_item_button_styles(character_button_refs, selected_character_names, 'ch', scene_number, cut_number)
    cmds.setParent('..')



def setup_prop_ui(found_props, scene_number, cut_number):
    global prop_button_refs, selected_prop_names
    prop_button_refs.clear()
    selected_prop_names.clear()

    if cmds.columnLayout("propUILayout", exists=True):
        children = cmds.columnLayout("propUILayout", q=True, ca=True) or []
        for child in children:
            cmds.deleteUI(child)

    prop_names = list(found_props.keys())  # ← unique_name 리스트

    for i in range(0, len(prop_names), PROPS_PER_ROW):
        row = cmds.rowLayout(
            numberOfColumns=PROPS_PER_ROW,
            columnWidth=[(j + 1, BUTTON_WIDTH) for j in range(PROPS_PER_ROW)],
            columnAlign=[(j + 1, 'center') for j in range(PROPS_PER_ROW)],
            columnAttach=[(j + 1, 'both', 0) for j in range(PROPS_PER_ROW)],
            height=BUTTON_HEIGHT,
            parent="propUILayout"
        )

        for j in range(PROPS_PER_ROW):
            if i + j < len(prop_names):
                unique_name = prop_names[i + j]
                group_path = found_props[unique_name]

                # 버튼 라벨은 unique_name 사용
                short_name_wrapped = split_name_to_two_lines(unique_name)

                has_cache, export_time = get_export_status(unique_name, 'prop', scene_number, cut_number)
                label = f"{short_name_wrapped}\n{export_time}" if has_cache else f"{short_name_wrapped}\nNo Cache"
                color = [0.3, 0.6, 1.0] if unique_name in selected_prop_names else (
                        [0.33, 0.43, 0.33] if has_cache else [0.43, 0.33, 0.33])

                btn = cmds.button(
                    label=label,
                    width=BUTTON_WIDTH,
                    height=BUTTON_HEIGHT,
                    backgroundColor=color,
                    command=lambda x, name=unique_name: handle_item_click(
                        name, prop_button_refs, selected_prop_names, 'prop', scene_number, cut_number
                    ),
                    parent=row
                )
                # 버튼과 연결된 데이터는 unique_name → group_path
                prop_button_refs[unique_name] = (btn, group_path)

        cmds.setParent('..')

    update_item_button_styles(prop_button_refs, selected_prop_names, 'prop', scene_number, cut_number)


def setup_bg_ui_animSet():
    global bg_button_refs, selected_bg_names
    bg_button_refs.clear()
    selected_bg_names.clear()

    bgs_per_row = PROPS_PER_ROW
    anim_set = "animSet"

    # 씬 안에서 BG 매칭 찾기
    bg_names_lower = [n.lower() for n in BG_NAMES]
    bgs_from_scene = find_bgs_in_scene()
    bg_names_from_list = []

    for ui_name, group_path in bgs_from_scene.items():
        base_name = ui_name.split("_")[0]
        if base_name.lower() in bg_names_lower:
            bg_names_from_list.append(group_path)


    # animSet과 BG 매칭 결과를 합침
    animset_names = sorted(cmds.sets(anim_set, query=True) or [], key=lambda name: name.split(":")[-1]) if cmds.objExists(anim_set) else []

    # 중복 제거한 전체 BG 목록
    all_bg_names = list(set(animset_names + bg_names_from_list))

    # UI 시작
    if not cmds.columnLayout("bgUILayout", exists=True):
        print("Warning: 'bgUILayout' not found.")
        return

    cmds.setParent("bgUILayout")
    children = cmds.columnLayout("bgUILayout", q=True, ca=True) or []
    for child in children:
        cmds.deleteUI(child)

    scene, cut = get_scene_and_cut()

    for i in range(0, len(all_bg_names), bgs_per_row):
        row_items = all_bg_names[i:i + bgs_per_row]
        row = cmds.rowLayout(
            numberOfColumns=len(row_items),
            columnWidth=[(j + 1, BUTTON_WIDTH) for j in range(len(row_items))],
            columnAlign=[(j + 1, 'center') for j in range(len(row_items))],
            columnAttach=[(j + 1, 'both', 0) for j in range(len(row_items))]
        )

        for j, full_name in enumerate(row_items):
            if not cmds.objExists(full_name):
                continue
            short_name = full_name.split(":")[-1]
            display_name = shorten_name_for_button(short_name)
            short_name_wrapped = split_name_to_two_lines(display_name)
            has_cache, export_time = get_export_status(short_name, 'bg', scene, cut)
            label = f"{short_name_wrapped}\n{export_time}" if has_cache else f"{short_name_wrapped}\nNo Cache"
            color = [0.33, 0.43, 0.33] if has_cache else [0.43, 0.33, 0.33]

            btn = cmds.button(
                label=label,
                width=BUTTON_WIDTH,
                height=BUTTON_HEIGHT,
                backgroundColor=color,
                command=lambda x, name=full_name: handle_item_click(name, bg_button_refs, selected_bg_names, 'bg', scene, cut)
            )

            bg_button_refs[full_name] = btn

        cmds.setParent('..')



def refresh_animout_ui(part):
    """
    part: 'bg', 'ch', 'prop', 'cam'
    """

    # # ✅ 선택 상태 초기화
    # if part == 'ch':
        # character_button_refs.clear()
        # selected_character_names.clear()
    # elif part == 'prop':
        # prop_button_refs.clear()
        # selected_prop_names.clear()
    # elif part == 'bg':
        # bg_button_refs.clear()
        # selected_bg_names.clear()
    # elif part == 'cam':
        # cam_button_refs.clear()
        # selected_cam_names.clear()

    ui_map = {
        'bg': ("bgUIFrame", "bgUILayout", setup_bg_ui_animSet),
        'ch': ("chUIFrame", "chUILayout", lambda: setup_character_ui(find_characters_in_scene(), *get_scene_and_cut())),
        'prop': ("propUIFrame", "propUILayout", lambda: setup_prop_ui(find_props_in_scene(), *get_scene_and_cut())),
        'cam': ("camUIFrame", "camUILayout", lambda: setup_camera_ui(*get_scene_and_cut()))
    }

    if part not in ui_map:
        print(f"❌ 알 수 없는 UI 파트: {part}")
        return

    frame_name, layout_name, setup_func = ui_map[part]

    if cmds.columnLayout(layout_name, exists=True):
        children = cmds.columnLayout(layout_name, q=True, ca=True) or []
        for child in children:
            if not cmds.objectTypeUI(child) == 'rowLayout':  # 버튼 줄 유지
                cmds.deleteUI(child)

    if cmds.frameLayout(frame_name, exists=True):
        cmds.setParent(layout_name)
        setup_func()
    else:
        print(f"❌ Frame '{frame_name}' not found. Cannot refresh {part} UI.")
        


def set_selected_as_published():
    category_sets = {
        'ch': (selected_character_names, CHARACTER_NAMES, 'ch'),
        'prop': (selected_prop_names, PROP_NAMES, 'prop'),
        'bg': (selected_bg_names, BG_NAMES, 'bg')
    }

    base_path = get_project_paths()

    for category_key, (selected_set, name_list, category_folder) in category_sets.items():
        for full_path in selected_set:
            if not cmds.objExists(full_path):
                continue
            short_name = full_path.split('|')[-1].split(':')[-1]  # 네임스페이스 제거
            ref_node = cmds.referenceQuery(full_path, referenceNode=True)
            if not ref_node:
                print(f"[INFO] {short_name}는 참조가 아닙니다. 스킵합니다.")
                continue

            publish_path = os.path.join(base_path, "assets", category_folder, short_name, f"{short_name}.mb")
            publish_path = os.path.normpath(publish_path)

            if not os.path.exists(publish_path):
                cmds.warning(f"퍼블리시 파일이 존재하지 않습니다: {publish_path}")
                continue

            try:
                cmds.file(publish_path, loadReference=ref_node, type="mayaBinary", options="v=0")
                print(f"✅ {short_name} → 퍼블리시 파일로 교체됨: {publish_path}")
            except Exception as e:
                cmds.warning(f"❌ {short_name} 교체 실패: {e}")

def init_browser_state():
    """
    실행 시 현재 열린 파일 우선 → 없거나 규칙 불일치면 JSON 상태 복원
    """
    current_file_path = cmds.file(query=True, sceneName=True)
    if current_file_path and is_valid_scene_file(current_file_path):
        # print("[AnimOut] 현재 열린 파일 기준으로 UI 갱신")
        update_menus_from_current_file()
    else:
        # print("[AnimOut] 현재 파일이 유효하지 않음 → 저장된 상태 복원 시도")
        restore_browser_state()

                
def restore_browser_state():
    state = load_browser_state()
    if not state:
        return

    try:
        # 프로젝트 먼저 세팅
        cmds.optionMenu(projectMenuName, edit=True, value=state["project"])
        update_scenes()

        # 씬 세팅 (존재 여부 확인)
        scene_items = cmds.optionMenu("sceneMenu", q=True, itemListLong=True) or []
        if scene_items:
            labels = [cmds.menuItem(i, q=True, label=True) for i in scene_items]
            if state["scene"] in labels:
                cmds.optionMenu("sceneMenu", e=True, value=state["scene"])
        update_cuts(selected_scene=state["scene"])

        # 컷 세팅
        cut_items = cmds.optionMenu("cutMenu", q=True, itemListLong=True) or []
        if cut_items:
            labels = [cmds.menuItem(i, q=True, label=True) for i in cut_items]
            if state["cut"] in labels:
                cmds.optionMenu("cutMenu", e=True, value=state["cut"])
        update_processes(selected_cut=state["cut"])

        # 프로세스 세팅
        proc_items = cmds.optionMenu("processMenu", q=True, itemListLong=True) or []
        if proc_items:
            labels = [cmds.menuItem(i, q=True, label=True) for i in proc_items]
            if state["process"] in labels:
                cmds.optionMenu("processMenu", e=True, value=state["process"])
        update_files(selected_process=state["process"])

        # 파일 세팅
        file_items = cmds.optionMenu("fileMenu", q=True, itemListLong=True) or []
        if file_items:
            labels = [cmds.menuItem(i, q=True, label=True) for i in file_items]
            if state["file"] in labels:
                cmds.optionMenu("fileMenu", e=True, value=state["file"])

        # print("[AnimOut] 상태 복원 완료")

    except Exception as e:
        cmds.warning(f"[AnimOut] 상태 복원 중 오류: {e}")



def rrAnimout_UI():
    window_name = "rrAnimout"
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)
    cmds.window(window_name, title="rrAnimout", width=304, height=510)


    # 전체 루트 columnLayout
    cmds.columnLayout("rootLayout", adjustableColumn=False, backgroundColor=[0.26, 0.26, 0.26])

    # 제목
    cmds.frameLayout(lv=0, mh=10, mw=8)
    cmds.text(label=" SF ANIMOUT_test", align='left', height=20, enableBackground=False)
    cmds.setParent('..')

    global projectMenuName
    current_project = get_current_project()
    set_current_project(current_project)

    # SCENE BROWSER
    cmds.frameLayout(cll=1, lv=1, l='SCENE BROWSER', fn="smallPlainLabelFont", mh=0, mw=8, backgroundColor=[0.26, 0.26, 0.26])
    cmds.columnLayout(adjustableColumn=False, backgroundColor=[0.29, 0.29, 0.29], co=('both', 3), rs=3)
    cmds.separator(height=1, style='none')

    cmds.rowLayout(numberOfColumns=2, columnWidth2=[50, 250], columnAlign=[(1, 'center'), (2, 'center')])
    projectMenuName = cmds.optionMenu(label="", height=30, width=276, changeCommand=update_project_settings, backgroundColor=[0.35, 0.35, 0.35])
    cmds.menuItem(label="THE_TRAP")
    cmds.menuItem(label="ARBO_BION")
    cmds.menuItem(label="BTS")    
    cmds.menuItem(label="CKR")    
    cmds.menuItem(label="DSC")
    cmds.menuItem(label="FUZZ")    
    cmds.optionMenu(projectMenuName, edit=True, value=current_project, changeCommand=update_scenes)
    cmds.setParent('..')

    cmds.rowLayout(numberOfColumns=3, columnWidth3=[90, 91, 91], columnAlign=[(1, 'center'), (2, 'center'), (3, 'center')])
    cmds.text(label="SCENE", height=20, width=90)
    cmds.text(label="CUT", height=20, width=91)
    cmds.text(label="PROCESS", height=20, width=91)
    cmds.setParent('..')

    cmds.rowLayout(numberOfColumns=3, columnWidth3=[90, 91, 91], columnAlign=[(1, 'center'), (2, 'center'), (3, 'center')])
    cmds.optionMenu('sceneMenu', changeCommand=update_cuts, height=30, width=90, backgroundColor=[0.35, 0.35, 0.35])
    cmds.optionMenu('cutMenu', changeCommand=update_processes, height=30, width=91, backgroundColor=[0.35, 0.35, 0.35])
    cmds.optionMenu('processMenu', changeCommand=update_files, height=30, width=91, backgroundColor=[0.35, 0.35, 0.35])
    cmds.setParent('..')

    cmds.rowLayout(numberOfColumns=1, columnWidth1=276, columnAlign=[(1, 'center')])
    cmds.optionMenu('fileMenu', height=30, width=276, backgroundColor=[0.35, 0.35, 0.35])
    scene, cut = get_scene_and_cut()
    camera = update_camera_name(scene, cut)
    cmds.setParent('..')

    cmds.rowLayout(numberOfColumns=2, columnWidth2=[45, 230])
    cmds.text(label='변경사항:', width=45, align='left')
    global changeDescriptionField
    changeDescriptionField = cmds.textField(width=230, backgroundColor=[0.15, 0.18, 0.18])
    cmds.setParent('..')


    cmds.rowLayout(numberOfColumns=4, columnWidth4=[67, 67, 68, 68], columnAlign=[(1, 'center'), (2, 'center'), (3, 'center'), (4, 'center')])
    cmds.button(label="파일열기", command=on_open_button_click, height=30, width=67, backgroundColor=[0.37, 0.37, 0.37])
    cmds.button(label="폴더열기", command=lambda *args: open_scene_folder(), height=30, width=67, backgroundColor=[0.37, 0.37, 0.37])
    cmds.button(label="+1 버전저장", command=lambda _: incremental_save(), height=30, width=68, backgroundColor=[0.37, 0.37, 0.37])
    cmds.button(label="퍼블리시", command=lambda _: aniPublish(), height=30, width=68, backgroundColor=[0.37, 0.37, 0.37])
    cmds.setParent('..')

    cmds.separator(height=10, style='none')
    cmds.setParent('..')  # columnLayout inside SCENE BROWSER
    cmds.setParent('..')  # frameLayout SCENE BROWSER

    # ANIMOUT 영역
    cmds.frameLayout(cll=1, lv=1, l='ANIMOUT', fn="smallPlainLabelFont", mh=0, mw=8, backgroundColor=[0.26, 0.26, 0.26])
    cmds.columnLayout("mainAnimoutColumn", adjustableColumn=False, backgroundColor=[0.29, 0.29, 0.29], co=('both', 3), rs=3)
    cmds.separator(height=1, style='none')

    # BGS TO OUT
    cmds.frameLayout("bgUIFrame", cll=1, lv=1, label="BGS TO OUT",
                     fn="smallPlainLabelFont", w=279, collapsable=False, mw=0, mh=0, backgroundColor=[0.23, 0.23, 0.23])
    cmds.columnLayout("bgWrapperLayout", width=279, adjustableColumn=0, co=('both', 0), rs=0, backgroundColor=[0.25, 0.25, 0.25])
    cmds.rowLayout(
        numberOfColumns=5,
        backgroundColor=[0.25, 0.25, 0.25],
        columnWidth5=[20, 20, 170, 30, 30],
        columnAlign=[(i, 'center') for i in range(1, 6)],
        columnAttach=[(i, 'both', 0) for i in range(1, 6)],
        height=18
    )
    cmds.iconTextButton(style='iconOnly', image1='cycle.png', backgroundColor=[0.23, 0.23, 0.23], w=20, h=18, command=lambda *args: refresh_animout_ui('bg'))
    cmds.button(label='✔', width=20, height=18, backgroundColor=[0.23, 0.23, 0.23], command=lambda *args: select_all_items('bg'))
    cmds.button(label="AnimOut BG", backgroundColor=[0.23, 0.23, 0.23], height=18, width=170, command=lambda *args: export_selected_items('bg'))
    cmds.button(label="+", height=18, width=30, backgroundColor=[0.23, 0.23, 0.23], command=add_selected_to_anim_set)
    cmds.button(label="-", height=18, width=30, backgroundColor=[0.23, 0.23, 0.23], command=remove_selected_from_anim_set)
    cmds.setParent('..')  # rowLayout
    cmds.columnLayout("bgUILayout", width=279, adjustableColumn=0, co=('both', 0), rs=0, backgroundColor=[0.25, 0.25, 0.25])
    setup_bg_ui_animSet()
    cmds.setParent('..')  # bgUILayout
    cmds.setParent('..')  # bgWrapperLayout
    cmds.setParent('..')  # bgUIFrame

    
    cmds.separator(height=2, style='none')
    
    # CHS TO OUT
    cmds.frameLayout("chUIFrame", cll=1, cl=0, lv=1, label="CHS TO OUT",
                     fn="smallPlainLabelFont", w=279, backgroundColor=[0.23, 0.23, 0.23], mh=0, mw=0)
    cmds.columnLayout("chWrapperLayout", width=279, adjustableColumn=0, co=('both', 0), rs=0, backgroundColor=[0.25, 0.25, 0.25])
    cmds.rowLayout(
        numberOfColumns=3,
        columnWidth3=[20, 20, 239],
        columnAlign=[(1, 'center'), (2, 'center'), (3, 'center')],
        columnAttach=[(1, 'both', 0), (2, 'both', 0), (3, 'both', 0)],
        height=18,
        backgroundColor=[0.25, 0.25, 0.25]
    )
    cmds.iconTextButton(style='iconOnly', image1='cycle.png', w=20, h=18, backgroundColor=[0.23, 0.23, 0.23], command=lambda *args: refresh_animout_ui('ch'))
    cmds.button(label='✔', width=20, height=18, backgroundColor=[0.23, 0.23, 0.23], command=lambda *args: select_all_items('ch'))
    cmds.button(label="AnimOut CH", width=239, height=18, backgroundColor=[0.23, 0.23, 0.23], command=lambda *args: export_selected_items('ch'))
    cmds.setParent('..')  # rowLayout
    cmds.columnLayout("chUILayout", width=279, adjustableColumn=0, co=('both', 0), rs=0, backgroundColor=[0.25, 0.25, 0.25])
    found_characters = find_characters_in_scene()
    setup_character_ui(found_characters, scene, cut)
    cmds.setParent('..')  # chUILayout
    cmds.setParent('..')  # chWrapperLayout
    cmds.setParent('..')  # chUIFrame

    cmds.separator(height=2, style='none')

    
    # PRP TO OUT
    cmds.frameLayout("propUIFrame", cll=1, cl=0, lv=1, label="PRP TO OUT",
                     fn="smallPlainLabelFont", w=279, backgroundColor=[0.23, 0.23, 0.23], mh=0, mw=0)
    cmds.columnLayout("propWrapperLayout", width=279, adjustableColumn=0, co=('both', 0), rs=0, backgroundColor=[0.25, 0.25, 0.25])
    cmds.rowLayout(
        numberOfColumns=3,
        columnWidth3=[20, 20, 239],
        columnAlign=[(i, 'center') for i in range(1, 4)],
        columnAttach=[(i, 'both', 0) for i in range(1, 4)],
        height=18  # 버튼과 딱 맞게
    )
    cmds.iconTextButton(style='iconOnly', image1='cycle.png', backgroundColor=[0.23, 0.23, 0.23], w=20, h=18, command=lambda *args: refresh_animout_ui('prop'))
    cmds.button(label='✔', width=20, height=18, backgroundColor=[0.23, 0.23, 0.23], command=lambda *args: select_all_items('prop'))
    cmds.button(label="AnimOut PROP", backgroundColor=[0.23, 0.23, 0.23], height=18, width=239, command=lambda *args: export_selected_items('prop'))
    cmds.setParent('..')  # rowLayout
    cmds.columnLayout("propUILayout", width=279, adjustableColumn=0, co=('both', 0), rs=0)
    found_props = find_props_in_scene()
    setup_prop_ui(found_props, scene, cut)
    cmds.setParent('..')  # propUILayout
    cmds.setParent('..')  # propWrapperLayout
    cmds.setParent('..')  # propUIFrame

    cmds.separator(height=2, style='none')

    # CAM TO OUT
    cmds.frameLayout("camUIFrame", cll=1, cl=0, lv=1, label="CAM TO OUT",
                     fn="smallPlainLabelFont", w=279, backgroundColor=[0.23, 0.23, 0.23], mh=0, mw=0)
    cmds.columnLayout("camWrapperLayout", width=279, adjustableColumn=0, co=('both', 0), rs=0, backgroundColor=[0.25, 0.25, 0.25])
    cmds.rowLayout(
        numberOfColumns=3,
        columnWidth3=[20, 20, 239],
        columnAlign=[(i, 'center') for i in range(1, 4)],
        columnAttach=[(i, 'both', 0) for i in range(1, 4)],
        height=18,
        backgroundColor=[0.25, 0.25, 0.25]
    )
    cmds.iconTextButton(style='iconOnly', image1='cycle.png', backgroundColor=[0.23, 0.23, 0.23], w=20, h=18, command=lambda *args: refresh_animout_ui('cam'))
    cmds.button(label='✔', width=20, height=18, backgroundColor=[0.23, 0.23, 0.23], command=lambda *args: select_all_items('cam'))
    cmds.button(label="AnimOut CAM", backgroundColor=[0.23, 0.23, 0.23], height=18, width=239, command=lambda *args: export_selected_items('cam'))
    cmds.setParent('..')  # rowLayout
    cmds.columnLayout("camUILayout", width=279, adjustableColumn=0, co=('both', 0), rs=0, backgroundColor=[0.25, 0.25, 0.25])
    setup_camera_ui(scene, cut)
    cmds.setParent('..')  # camUILayout
    cmds.setParent('..')  # camWrapperLayout
    cmds.setParent('..')  # camUIFrame

    cmds.separator(height=5, style='none')
    
    # AnimOut 버튼
    cmds.frameLayout("animoutFrame", cll=0, lv=0, l='ANIMOUT', fn="smallPlainLabelFont", w=279, mh=0, mw=0, backgroundColor=[0.26, 0.26, 0.26])
    cmds.rowLayout(numberOfColumns=1, columnWidth1=279, columnAlign=[(1, 'center')])
    cmds.button(label="선택 어셋을 퍼블리시로 변경", height=30, width=276, backgroundColor=[0.35, 0.4, 0.4], command=lambda *args: set_selected_as_published())
    cmds.setParent('..')
    cmds.rowLayout(numberOfColumns=2, columnWidth2=[138, 138], columnAlign=[(1, 'center'), (2, 'center')])
    cmds.button(label="AnimOut_Selected", height=30, backgroundColor=[0.4, 0.4, 0.4], width=138, command=lambda *args: export_Selected())
    cmds.button(label="AnimOut_All", height=30, backgroundColor=[0.4, 0.4, 0.4], width=138, command=lambda *args: export_all())
    cmds.setParent('..')
    # 기존 두 개 버튼 아래에 단독 줄 추가
    cmds.rowLayout(numberOfColumns=1, columnWidth1=276, columnAlign=[(1, 'center')])    
    cmds.button(label="Export ▶ 씬선택 카메라", height=30, backgroundColor=[0.35, 0.4, 0.4], width=276, command=export_selected_camera_from_scene)   
    cmds.setParent('..')
    cmds.separator(height=2, style='none')
    cmds.setParent('..')  # columnLayout mainAnimoutColumn
    cmds.setParent('..')  # frameLayout ANIMOUT

    # CLOTH CONTROL
    cmds.frameLayout(cll=1, lv=1, cl=1, l='CLOTH CONTROL', fn="smallPlainLabelFont", mh=0, mw=8, backgroundColor=[0.26, 0.26, 0.26])
    cmds.columnLayout(adjustableColumn=False, backgroundColor=[0.29, 0.29, 0.29], co=('both', 3), rs=3)
    cmds.separator(height=1, style='none')
    cmds.rowLayout(numberOfColumns=1, columnWidth1=(279), columnAlign=[(1, 'center')])
    cmds.optionMenu('minTimeMenu', height=30 ,width=279 , label='CFX Start Frame  :  ')
    cmds.menuItem(label='1')
    cmds.menuItem(label='50')
    cmds.menuItem(label='70')
    cmds.menuItem(label='80')
    cmds.menuItem(label='100')
    cmds.menuItem(label='101')
    cmds.menuItem(label='700')
    cmds.optionMenu('minTimeMenu', height=30 ,width=279 , edit=True, value='101')
    cmds.setParent('..')
    cmds.rowLayout(numberOfColumns=2, columnWidth2=[140, 140], columnAlign=[(1, 'center'), (2, 'center')])
    cmds.button(label="Export Avatar", backgroundColor=[0.4, 0.4, 0.4], height=30, width=140, command=lambda *args: export_avatar())
    cmds.button(label="Export Garment", backgroundColor=[0.4, 0.4, 0.4], height=30, width=140, command=lambda *args: export_garment())
    cmds.setParent('..')
    cmds.separator(height=2, style='none')
    cmds.setParent('..')
    cmds.separator(height=5, style='none')
    cmds.setParent('..')
    cmds.setParent('..')

    init_browser_state()



    cmds.showWindow()
    refresh_ui_on_new_file()



def on_open_button_click(*args):
    result = cmds.confirmDialog(
        title='Open File?',
        message='Do you want to open the file?',
        button=['OK', 'Cancel'],
        defaultButton='OK',
        cancelButton='Cancel',
        dismissString='Cancel'
    )
    if result == 'OK':
        load_selected_asset("open")

cmds.evalDeferred(lambda *args: remove_malicious_nodes())
rrAnimout_UI()

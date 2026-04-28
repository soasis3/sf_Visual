bl_info = {
    "name": "rrRender",
    "blender": (3, 0, 0),
    "category": "SF_Tools",
    "author": "Sean Hwang",
    "version": (1, 1),
    "location": "View3D > UI > SF_Render",
    "description": "This addon provides a simple way to reference and delete Rendering in Blender.",
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
}

import bpy
from bpy.types import Operator
import os
import re
import json
import threading
from operator import itemgetter
import math
from mathutils import Vector
import sys
import shutil
import importlib
from datetime import datetime

# -------------------------------------------------------------------
# ✅ [Global] 프로젝트별 설정 정의 (단일 소스)
# -------------------------------------------------------------------
PROJECT_CONFIG = {
    'THE_TRAP': {
        'drive': "T:/",
        'prefix': "ttm",
        'cache_dir': "ren/cache",
        'publish_dir': "pub",
    },
    'ARBOBION': {
        'drive': "A:/",
        'prefix': "ab",
        'cache_dir': "ren/cache",
        'publish_dir': "pub",
    },
    'DSC': {
        'drive': "S:/",
        'prefix': "DSC",
        'cache_dir': "ren/cache",
        'publish_dir': "pub",
    },
    'BTS': {
        'drive': "B:/",
        'prefix': "BTS",
        'cache_dir': "ren/cache",
        'publish_dir': "pub",
    },
    'FUZZ': {
        'drive': "Z:/",
        'prefix': "FUZZ",
        'cache_dir': "ren/cache",
        'publish_dir': "pub",
    },
}

PROJECT_NAME_ALIASES = {
    'THE_TRAP': 'THE_TRAP',
    'TTM': 'THE_TRAP',
    'ARBOBION': 'ARBOBION',
    'ARBO_BION': 'ARBOBION',
    'ARB': 'ARBOBION',
    'DSC': 'DSC',
    'BTS': 'BTS',
    'FUZZ': 'FUZZ',
}


def get_current_project_name(default='BTS'):
    """현재 UI의 프로젝트 이름을 정규화하여 반환"""
    try:
        raw_name = bpy.context.scene.my_project_settings.projects
    except Exception:
        raw_name = default

    raw_name = str(raw_name).strip()
    if not raw_name:
        raw_name = default

    return PROJECT_NAME_ALIASES.get(raw_name.upper(), raw_name.upper())


def get_config_by_project_name(project_name=None):
    normalized = get_current_project_name() if project_name is None else PROJECT_NAME_ALIASES.get(str(project_name).strip().upper(), str(project_name).strip().upper())
    return PROJECT_CONFIG.get(normalized, PROJECT_CONFIG['BTS'])


def get_current_config():
    return PROJECT_CONFIG.get(get_current_project_name(), PROJECT_CONFIG['BTS'])


def get_project_paths(project_name=None):
    return get_config_by_project_name(project_name)['drive']


def get_project_prefix(project_name=None):
    return get_config_by_project_name(project_name)['prefix']



# ✅ 외부 rrRender.py 파일 경로
SCRIPT_PATH = r"M:\RND\SFtools\2023\render\rrRender.py"
SCRIPT_BACKUP_DIR = r"M:\RND\SFtools\2023\render\_t"
DEPLOY_ALLOWED_USERS = {"hwang"}
HWANG_LOCAL_SCRIPT_PATH = r"C:\Users\hwang\Desktop\codex\rrRender\rrRender.py"

# ✅ 현재 모듈 이름 (import할 때 씀)
MODULE_NAME = "rrRender"

# ✅ 마지막으로 불러온 수정 시간
last_mtime = None


def normalize_path(path):
    return os.path.normcase(os.path.abspath(path))


def can_show_deploy_tools():
    return os.environ.get("USERNAME", "").strip().lower() in {user.lower() for user in DEPLOY_ALLOWED_USERS}


def get_update_source_path():
    if os.environ.get("USERNAME", "").strip().lower() == "hwang":
        return HWANG_LOCAL_SCRIPT_PATH
    return SCRIPT_PATH


def get_next_script_backup_path(target_path=SCRIPT_PATH, backup_dir=SCRIPT_BACKUP_DIR):
    """_t 폴더의 기존 백업 파일명을 훑어서 다음 버전 경로를 반환한다."""
    base_name = os.path.splitext(os.path.basename(target_path))[0]
    extension = os.path.splitext(target_path)[1]
    version_pattern = re.compile(
        rf"^{re.escape(base_name)}_v(\d+)(?:.*){re.escape(extension)}$",
        re.IGNORECASE,
    )

    max_version = 0
    if os.path.isdir(backup_dir):
        for file_name in os.listdir(backup_dir):
            match = version_pattern.match(file_name)
            if not match:
                continue
            max_version = max(max_version, int(match.group(1)))

    next_version = max_version + 1
    backup_name = f"{base_name}_v{next_version:03d}{extension}"
    return os.path.join(backup_dir, backup_name), next_version

class DEV_OT_reload_rrrender(bpy.types.Operator):
    """외부 rrRender.py 다시 불러오기"""
    bl_idname = "dev.reload_rrrender"
    bl_label = "Update Script"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        module_name = "rrRender"
        source_path = get_update_source_path()

        if module_name in sys.modules:
            mod = sys.modules[module_name]
            local_path = os.path.abspath(mod.__file__)
        else:
            self.report({'ERROR'}, f"{module_name} 모듈을 찾을 수 없음")
            return {'CANCELLED'}

        # 서버 → 로컬 복사
        try:
            shutil.copy2(source_path, local_path)
            self.report({'INFO'}, f"{source_path} → {local_path} 복사 완료")
        except Exception as e:
            self.report({'ERROR'}, f"복사 실패: {e}")
            return {'CANCELLED'}

        # 🔄 Blender 전체 스크립트 리로드
        bpy.ops.script.reload()

        return {'FINISHED'}


class DEV_OT_deploy_rrrender(bpy.types.Operator):
    """현재 로컬 rrRender.py를 서버 경로로 배포하고 기존 배포본은 _t에 버전 백업"""
    bl_idname = "dev.deploy_rrrender"
    bl_label = "Deploy Script"
    bl_options = {'REGISTER', 'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        local_path = os.path.abspath(__file__)
        target_path = SCRIPT_PATH
        backup_dir = SCRIPT_BACKUP_DIR

        if not can_show_deploy_tools():
            self.report({'WARNING'}, "허용된 사용자만 배포할 수 있습니다.")
            return {'CANCELLED'}

        if not os.path.exists(local_path):
            self.report({'ERROR'}, f"로컬 스크립트를 찾을 수 없음: {local_path}")
            return {'CANCELLED'}

        if normalize_path(local_path) == normalize_path(target_path):
            self.report({'WARNING'}, "현재 스크립트가 이미 배포 경로에서 실행 중입니다.")
            return {'CANCELLED'}

        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            os.makedirs(backup_dir, exist_ok=True)

            backup_path = None
            if os.path.exists(target_path):
                backup_path, version_number = get_next_script_backup_path(target_path, backup_dir)
                shutil.copy2(target_path, backup_path)
                print(f"[DEPLOY] 기존 배포본 백업 완료: v{version_number:03d} -> {backup_path}")

            shutil.copy2(local_path, target_path)
            message = f"배포 완료: {local_path} -> {target_path}"
            if backup_path:
                message += f" | backup: {os.path.basename(backup_path)}"
            self.report({'INFO'}, message)
            print(f"[DEPLOY] {message}")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, f"배포 실패: {exc}")
            return {'CANCELLED'}


# import sf_blendLdv
# if script_path not in sys.path:
    # sys.path.append(script_path)
# SF_OT_AddPropertiesAndLink 클래스를 임포트
# from sf_blendLdv import SF_OT_AddPropertiesAndLink
# from sf_blendLdv import SF_OT_LinkCharacterLights
# from SF_OT_AddPropertiesAndLink import SF_OT_AddPropertiesAndLink
# from SF_OT_LinkCharacterLights import SF_OT_LinkCharacterLights

# from sf_blendLdv import SF_OT_LinkRimToNode
# from SF_OT_LinkRimtoNode import SF_OT_LinkRimToNode

# from sf_blendLdv import MyProjectSettings

################################################################
######################### Basic Preperation ####################
################################################################

# # 파일 경로에서 씬과 컷 번호 추출 함수
# def extract_scene_cut_from_filename(filepath):
    # filename = os.path.basename(filepath)
    # project_prefix = get_project_prefix()  # 프로젝트 접두사를 가져옵니다.
    # regex_pattern = fr'{project_prefix}_(\d{4})_(\d{4})_ren_v\d{3}\.blend'  # 프로젝트 접두사를 사용한 정규 표현식
    # match = re.match(regex_pattern, filename)

    # # match = re.match(r'ttm_(\d{4})_(\d{4})_ren_v\d{3}\.blend', filename)
    # if match:
        # scene_number, cut_number = match.groups()
        # return scene_number, cut_number
    # return None, None
def extract_scene_cut_from_filename(filepath):
    if not filepath: 
        return None, None
        
    import os
    import re
    filename = os.path.basename(filepath)
    project_prefix = get_project_prefix()  # 프로젝트 접두사를 가져옵니다.
    
    # ✅ 핵심: f-string 안에서 정규식 중괄호를 쓰려면 {{ }} 처럼 두 번 써야 합니다!
    # 그리고 _ch 등이 붙은 파일도 인식하도록 패턴을 깔끔하게 다듬었습니다.
    regex_pattern = fr'{project_prefix}_(\d{{4}})_(\d{{4}})'
    match = re.search(regex_pattern, filename)

    if match:
        scene_number, cut_number = match.groups()
        return scene_number, cut_number
    return None, None

def get_character_dir():
    base_path = get_project_paths()
    return os.path.join(base_path, "assets", "ch")

def get_background_dir():
    base_path = get_project_paths()
    return os.path.join(base_path, "assets", "bg")

def get_prop_dir():
    base_path = get_project_paths()
    return os.path.join(base_path, "assets", "prop")

# ---- helper: 인스턴스 꼬리('_<숫자>')만 안전하게 제거 ----
def get_asset_base_name(name: str) -> str:
    """
    이름 끝에 '_<숫자>' 패턴이 있을 때만 그 꼬리를 제거해 base_name 반환.
    예) 'chage_1' -> 'chage', 'boxE_12' -> 'boxE'
        중간에 '_'가 있는 이름(police_box_E)은 그대로 둠.
    """
    head, sep, tail = name.rpartition('_')
    if sep and tail.isdigit():
        return head
    return name


# 디렉토리 내의 하위 폴더 이름을 가져오는 함수
def get_subfolder_names(directory, include_word=None, exclude_word=None):
    subfolder_names = [name for name in os.listdir(directory) 
                       if os.path.isdir(os.path.join(directory, name)) 
                       and (include_word is None or include_word in name) 
                       and (exclude_word is None or exclude_word not in name)]
    # print(f"Directory: {directory}")
    # print(f"Include Word: {include_word}, Exclude Word: {exclude_word}")
    # print(f"Subfolder Names: {subfolder_names}")
    return subfolder_names

def get_character_names():
    character_dir = get_character_dir()
    names = get_subfolder_names(character_dir)
    return [name for name in names if not name.startswith('light')]

def get_bg_names():
    background_dir = get_background_dir()
    names = get_subfolder_names(background_dir)
    return names

def get_prop_names():
    prop_dir = get_prop_dir()
    names = get_subfolder_names(prop_dir)
    non_floor_names = [name for name in names if not name.startswith('floor')]
    return non_floor_names


def find_asset_file_path(directory, asset_name):
    pattern = re.compile(rf"_{asset_name}\.usd$")
    # print(f"Searching in directory: {directory} for asset: {asset_name}")
    for file in os.listdir(directory):
        print(f"Checking file: {file}")
        if pattern.search(file):
            print(f"Found matching file: {file}")
            return os.path.join(directory, file)
    print("No matching file found.")
    return None

def get_category_name(self, asset_name):
    # 동적으로 이름 목록을 가져오기
    character_names = get_character_names()
    bg_names = get_bg_names()
    prop_names = get_prop_names()

    # 기존 카테고리 결정 로직
    if asset_name in character_names:
        return "ch"
    elif asset_name in bg_names:
        return "bg"
    elif asset_name in prop_names:
        return "prop"
    else:
        return "prop"

################################################################
#########################Scene Browser Operation################
################################################################
# 캐시 데이터 구조
cache = {
    "scenes": {},
    "cuts": {}
}

def open_folder(path):
    if os.path.exists(path):
        if os.name == 'nt':  # Windows
            os.startfile(path)
        elif os.name == 'posix':  # macOS, Linux
            subprocess.Popen(['xdg-open', path])

class OpenSceneFolderOperator(bpy.types.Operator):
    bl_idname = "file.open_scene_folder"
    bl_label = "Open Scene Folder"

    @classmethod
    def poll(cls, context):
        return context.scene.my_tool.scene_number != ''

    def execute(self, context):
        base_path = get_project_paths()
        scene_number = context.scene.my_tool.scene_number
        path = os.path.join(base_path, "scenes", scene_number)
        open_folder(path)
        return {'FINISHED'}

class OpenCutFolderOperator(bpy.types.Operator):
    bl_idname = "file.open_cut_folder"
    bl_label = "Open Cut Folder"

    @classmethod
    def poll(cls, context):
        return context.scene.my_tool.cut_number != ''

    def execute(self, context):
        scene_number = context.scene.my_tool.scene_number
        cut_number = context.scene.my_tool.cut_number
        base_path = get_project_paths()
        path = os.path.join(base_path, "scenes", scene_number, cut_number)
        open_folder(path)
        return {'FINISHED'}
    
class MyProjectSettings1(bpy.types.PropertyGroup):
    projects: bpy.props.EnumProperty(
        name="Projects",
        description="Select a project",
        items=[
            ('THE_TRAP', "The Trap Movie", "Located in T:\\ drive"),
            ('ARBOBION', "Arbo&Bion", "Located in A:\\ drive"),
            ('DSC', "DSC", "Located in S:\\ drive"),
            ('BTS', "BTS", "Located in B:\\ drive"),            
            ('FUZZ', "FUZZ", "Located in Z:\\ drive")
        ]
    )
    
# 씬 목록을 캐시에서 가져오거나, 없으면 로드
def get_cached_scenes():
    base_path = get_project_paths()
    scene_path = os.path.join(base_path, "scenes")
    if scene_path in cache["scenes"]:
        return cache["scenes"][scene_path]

    scenes = []
    if os.path.exists(scene_path):
        for scene in sorted(os.listdir(scene_path)):
            if (
                os.path.isdir(os.path.join(scene_path, scene)) and
                not scene.startswith('.') and
                not scene.startswith('_')
            ):
                scenes.append((scene, scene, ""))

    cache["scenes"][scene_path] = scenes
    return scenes


# 컷 목록을 캐시에서 가져오거나, 없으면 로드
def get_cached_cuts(scene_number):
    base_path = get_project_paths()
    cut_path = os.path.join(base_path, "scenes", scene_number)
    if cut_path in cache["cuts"]:
        return cache["cuts"][cut_path]

    cuts = []
    if os.path.exists(cut_path):
        for cut in sorted(os.listdir(cut_path)):
            if (
                os.path.isdir(os.path.join(cut_path, cut)) and
                not cut.startswith('.') and
                not cut.startswith('_')
            ):
                cuts.append((cut, cut, ""))

    cache["cuts"][cut_path] = cuts
    return cuts


def is_valid_folder(name):
    return not (name.startswith('_') or 'omit' in name.lower() or '-' in name)

def get_scene_numbers(self, context):
    base_path = get_project_paths()
    scene_path = os.path.join(base_path, "scenes")

    # 파일 경로가 없는 경우 기본값 반환
    if not os.path.exists(scene_path):
        return [("NO_FILE", "No File", "No file found")]

    items = []
    for scene in sorted(os.listdir(scene_path)):
        if os.path.isdir(os.path.join(scene_path, scene)) and is_valid_folder(scene):
            items.append((scene, scene, ""))

    return items if items else [("NO_SCENES", "No Scenes", "No scenes available")]

def get_cut_numbers(self, context):
    scene_number = context.scene.my_tool.scene_number
    base_path = get_project_paths()
    cut_path = os.path.join(base_path, "scenes", scene_number)

    if not os.path.exists(cut_path):
        return [("NO_FILE", "No File", "No cuts found")]

    items = []
    for cut in sorted(os.listdir(cut_path)):
        if os.path.isdir(os.path.join(cut_path, cut)) and is_valid_folder(cut):
            items.append((cut, cut, ""))

    return items if items else [("NO_CUTS", "No Cuts", "No cuts available")]




def get_blend_files(self, context):
    scene_number = context.scene.my_tool.scene_number
    cut_number = context.scene.my_tool.cut_number
    base_path = get_project_paths()
    project_prefix = get_project_prefix()
    blend_path = os.path.join(base_path, "scenes", scene_number, cut_number, "ren")
    if not os.path.exists(blend_path):
        return []

    files_with_time = []
    for file in os.listdir(blend_path):
        if file.endswith('.blend'):
            full_path = os.path.join(blend_path, file)
            modified_time = os.path.getmtime(full_path)
            files_with_time.append((file, modified_time))

    # 파일을 수정된 시간에 따라 내림차순으로 정렬
    sorted_files = sorted(files_with_time, key=itemgetter(1), reverse=True)
    
    # 파일 이름만 EnumProperty에 넣기
    items = []
    for file, _ in sorted_files:
        file = file.replace(f"{project_prefix}_{scene_number}_{cut_number}_ren_", "")
        file = os.path.splitext(file)[0]
        items.append((file, file, ""))
    return items
    
# Open 버튼에 연결할 함수
class OpenFileOperator(bpy.types.Operator):
    bl_idname = "file.open_file"
    bl_label = "Open File"

    @classmethod
    def poll(cls, context):
        return context.scene.my_tool.blend_file != ''

    def execute(self, context):
        scene_number = context.scene.my_tool.scene_number
        cut_number = context.scene.my_tool.cut_number
        blend_file = context.scene.my_tool.blend_file
        base_path = get_project_paths()
        project_prefix = get_project_prefix()
        file_path = os.path.join(base_path, "scenes", scene_number, cut_number, "ren", f"{project_prefix}_{scene_number}_{cut_number}_ren_{blend_file}.blend")
        bpy.ops.wm.open_mainfile(filepath=file_path)

        # 파일 경로에서 씬과 컷 번호 추출
        scene_number, cut_number = extract_scene_cut_from_filename(file_path)
        if scene_number and cut_number:
            context.scene.my_tool.scene_number = scene_number
            context.scene.my_tool.cut_number = cut_number

        return {'FINISHED'}


class AppendSceneOperator(bpy.types.Operator):
    bl_idname = "file.append_scene"
    bl_label = "Append Scene"
    asset_path: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return context.scene.my_tool.blend_file != ''

    def execute(self, context):
        scene_number = context.scene.my_tool.scene_number
        cut_number = context.scene.my_tool.cut_number
        blend_file = context.scene.my_tool.blend_file
        base_path = get_project_paths()
        project_prefix = get_project_prefix()
        self.asset_path = os.path.join(base_path, "scenes", scene_number, cut_number, "ren", f"{project_prefix}_{scene_number}_{cut_number}_ren_{blend_file}.blend")
        # 선택한 어셋 파일 내의 모든 씬을 가져옵니다.
        with bpy.data.libraries.load(self.asset_path, link=False) as (data_from, data_to):
            data_to.scenes = data_from.scenes
        
        return {'FINISHED'}
        
class SF_OT_RefreshSceneAndCutCache(bpy.types.Operator):
    bl_idname = "sf.refresh_scene_and_cut_cache"
    bl_label = "🔁 Refresh Scenes & Cuts"

    def execute(self, context):
        base_path = get_project_paths()
        scene_path = os.path.join(base_path, "scenes")
        cache["scenes"].pop(scene_path, None)

        scene_number = context.scene.my_tool.scene_number
        if scene_number:
            cut_path = os.path.join(base_path, "scenes", scene_number)
            cache["cuts"].pop(cut_path, None)
            self.report({'INFO'}, f"Refreshed cache for scenes and cuts of scene {scene_number}")
        else:
            self.report({'INFO'}, "Scene list refreshed. (No scene selected, so cut not refreshed)")

        return {'FINISHED'}

def update_scene_number(self, context):
    if hasattr(context.scene, "my_tool") and hasattr(context.scene.my_tool, "blend_file"):
        context.scene.my_tool.blend_file = ''
    context.scene.sf_scene_number = self.scene_number

def update_cut_number(self, context):
    if hasattr(context.scene, "my_tool") and hasattr(context.scene.my_tool, "blend_file"):
        context.scene.my_tool.blend_file = ''
    context.scene.sf_cut_number = self.cut_number

class MyProperties(bpy.types.PropertyGroup):
    scene_number: bpy.props.EnumProperty(
        name="Scene",
        description="Choose a Scene Number",
        items=lambda self, context: get_cached_scenes(),
        update=update_scene_number
    )

    cut_number: bpy.props.EnumProperty(
        name="Cut",
        description="Choose a Cut Number",
        items=lambda self, context: get_cached_cuts(context.scene.my_tool.scene_number),
        update=update_cut_number
    )


    blend_file: bpy.props.EnumProperty(
        name="File",
        description="Choose a Blender File",
        items=get_blend_files
    )

    confirm_overwrite: bpy.props.BoolProperty(
        name="Confirm Overwrite",
        description="Confirm before overwriting files",
        default=False
    )
    custom_prefix: bpy.props.StringProperty(
        name="Custom Prefix",
        default="",
        description="사용자 정의 접두사"
    )

    sfpaint_emission_strength: bpy.props.FloatProperty(
        name="Emisstion Strengh",
        description="Set Strength input on SF_Paint* node groups across all materials",
        default=0.2,
        min=0.0,
        soft_max=10.0
    )
    
    sfpaint_mask_int: bpy.props.FloatProperty(
        name="Mask_Int",
        default=1.0,
        min=0.0,
        soft_max=10.0
    )

    sfpaint_brusk_int: bpy.props.FloatProperty(
        name="Brusk_Int",
        default=0.02,
        min=0.0,
        soft_max=10.0
    )

    sfpaint_noise_int: bpy.props.FloatProperty(
        name="Noise Int",
        default=0.02,
        min=0.0,
        soft_max=10.0
    )    


    custom_suffix: bpy.props.StringProperty(name="Custom Suffix", default="")

################################################################
#########################Scene Build Operation##################
################################################################


# -------------------------------------------------------------------
# ✅ [Output Format Compatibility] Blender 4.1 ~ 5.1
# -------------------------------------------------------------------
# Blender 5.0부터 ImageFormatSettings.file_format enum이 media_type에 의해
# 필터링됩니다. 예를 들어 media_type이 VIDEO 상태면 file_format enum에는
# FFMPEG만 남아서, 곧바로 PNG/OPEN_EXR_MULTILAYER를 넣으면 TypeError가 납니다.
# 그래서 모든 Output / File Output Node 포맷 변경은 아래 헬퍼를 통해 처리합니다.

_IMAGE_OUTPUT_FORMATS = {
    'BMP', 'IRIS', 'PNG', 'JPEG', 'JPEG2000', 'TARGA', 'TARGA_RAW',
    'CINEON', 'DPX', 'OPEN_EXR', 'OPEN_EXR_MULTILAYER', 'TIFF', 'WEBP',
}
_VIDEO_OUTPUT_FORMATS = {'FFMPEG', 'AVI_JPEG', 'AVI_RAW'}


def _enum_identifiers(rna_owner, prop_name):
    """RNA enum identifier 리스트를 안전하게 반환."""
    try:
        prop = rna_owner.bl_rna.properties.get(prop_name)
        if not prop:
            return []
        return [item.identifier for item in prop.enum_items]
    except Exception:
        return []


def _set_enum_if_available(rna_owner, prop_name, value, label=""):
    """해당 enum 값이 사용 가능할 때만 설정. 실패하면 False."""
    if not hasattr(rna_owner, prop_name):
        return False

    try:
        available = _enum_identifiers(rna_owner, prop_name)
        if available and value not in available:
            print(f"[OutputCompat][SKIP] {label}{prop_name}='{value}' not in {available}")
            return False
        setattr(rna_owner, prop_name, value)
        return True
    except Exception as e:
        print(f"[OutputCompat][FAIL] {label}{prop_name}='{value}' ({e})")
        return False


def _wanted_media_type_for_file_format(file_format):
    fmt = str(file_format).upper()
    if fmt in _VIDEO_OUTPUT_FORMATS:
        # Blender 빌드에 따라 식별자가 VIDEO 또는 MOVIE일 가능성을 모두 방어.
        return ('VIDEO', 'MOVIE')
    # rrRender의 PNG / EXR / TGA 계열은 모두 IMAGE.
    return ('IMAGE',)


def _set_media_type_for_file_format(format_settings, file_format, label=""):
    """Blender 5.x용 media_type 선세팅. 4.x에서는 media_type이 없어서 자동 패스."""
    if not hasattr(format_settings, "media_type"):
        return True

    available = _enum_identifiers(format_settings, "media_type")
    candidates = _wanted_media_type_for_file_format(file_format)

    for candidate in candidates:
        if not available or candidate in available:
            try:
                format_settings.media_type = candidate
                return True
            except Exception as e:
                print(f"[OutputCompat][WARN] {label}media_type='{candidate}' 실패: {e}")

    print(f"[OutputCompat][WARN] {label}media_type 후보 {candidates} 적용 실패. available={available}")
    return False


def set_output_image_format(format_settings, file_format, color_mode=None, color_depth=None,
                            exr_codec=None, compression=None, label=""):
    """
    Blender 4.1~5.1 공용 Output Format setter.

    사용 대상:
      - scene.render.image_settings
      - CompositorNodeOutputFile.format

    핵심:
      Blender 5.x에서는 file_format 설정 전에 media_type을 IMAGE/VIDEO로 먼저 맞춘다.
    """
    if format_settings is None:
        print(f"[OutputCompat][FAIL] {label}format_settings is None")
        return False

    fmt = str(file_format).upper()
    ok = True

    _set_media_type_for_file_format(format_settings, fmt, label=label)

    try:
        format_settings.file_format = fmt
    except TypeError:
        # media_type이 꼬였거나 예외적인 빌드일 때, 가능한 media_type 전부 돌면서 재시도.
        applied = False
        if hasattr(format_settings, "media_type"):
            for media_type in _enum_identifiers(format_settings, "media_type"):
                try:
                    format_settings.media_type = media_type
                    format_settings.file_format = fmt
                    applied = True
                    break
                except Exception:
                    continue
        if not applied:
            ok = False
            print(f"[OutputCompat][FAIL] {label}file_format='{fmt}' 적용 실패")
    except Exception as e:
        ok = False
        print(f"[OutputCompat][FAIL] {label}file_format='{fmt}' ({e})")

    # file_format 설정 후에 세부 옵션 적용. 포맷별 지원 안 되는 enum은 조용히 스킵.
    if color_mode is not None:
        _set_enum_if_available(format_settings, "color_mode", str(color_mode).upper(), label=label)
    if color_depth is not None:
        _set_enum_if_available(format_settings, "color_depth", str(color_depth), label=label)
    if exr_codec is not None and hasattr(format_settings, "exr_codec"):
        _set_enum_if_available(format_settings, "exr_codec", str(exr_codec).upper(), label=label)
    if compression is not None and hasattr(format_settings, "compression"):
        try:
            format_settings.compression = int(compression)
        except Exception as e:
            print(f"[OutputCompat][WARN] {label}compression='{compression}' 적용 실패: {e}")

    return ok


def set_output_png(format_settings, alpha=False, label=""):
    return set_output_image_format(
        format_settings,
        'PNG',
        color_mode='RGBA' if alpha else 'RGB',
        color_depth='8',
        label=label,
    )


def set_output_exr_multilayer(format_settings, label=""):
    return set_output_image_format(
        format_settings,
        'OPEN_EXR_MULTILAYER',
        color_mode='RGBA',
        color_depth='16',
        exr_codec='PXR24',
        label=label,
    )



# -------------------------------------------------------------------
# ✅ Blender 4.1~5.1 Compositor NodeTree Compatibility
# -------------------------------------------------------------------
def get_scene_compositor_tree(scene=None, create=False, name=None):
    """
    Blender 4.x / 5.x 공용 Compositor NodeTree getter.

    Blender 4.x:
      - scene.use_nodes / scene.node_tree 사용

    Blender 5.x:
      - scene.node_tree 제거됨
      - scene.compositing_node_group 사용
    """
    if scene is None:
        scene = bpy.context.scene

    # Blender 5.0+
    if hasattr(scene, "compositing_node_group"):
        tree = getattr(scene, "compositing_node_group", None)
        if tree is None and create:
            tree_name = name or f"{scene.name}_Compositing"
            try:
                tree = bpy.data.node_groups.new(name=tree_name, type='CompositorNodeTree')
                scene.compositing_node_group = tree
                print(f"[CompositorCompat] Created compositing_node_group: {tree.name}")
            except Exception as e:
                print(f"[CompositorCompat][WARN] compositing_node_group 생성 실패: {e}")
                return None
        return tree

    # Blender 4.x
    if create and hasattr(scene, "use_nodes"):
        try:
            scene.use_nodes = True
        except Exception as e:
            print(f"[CompositorCompat][WARN] scene.use_nodes=True 실패: {e}")

    return getattr(scene, "node_tree", None)


def set_scene_compositor_enabled(scene=None, enabled=True, create_tree=False):
    """Blender 4.x/5.x 공용 compositor 활성 처리. 5.x에서는 node group 방식만 안전하게 처리."""
    if scene is None:
        scene = bpy.context.scene

    if hasattr(scene, "use_nodes"):
        try:
            scene.use_nodes = bool(enabled)
        except Exception as e:
            print(f"[CompositorCompat][WARN] scene.use_nodes={enabled} 실패: {e}")

    if enabled and (create_tree or hasattr(scene, "compositing_node_group")):
        return get_scene_compositor_tree(scene, create=create_tree)

    return get_scene_compositor_tree(scene, create=False)


def set_nested_property(target_obj, key_path, value):
    """
    점(.)으로 구분된 경로를 타고 들어가서 값을 설정하는 똑똑한 함수
    예: set_nested_property(scene.render, "image_settings.file_format", "OPEN_EXR")
    """
    try:
        # 경로 분해 (예: ['image_settings', 'file_format'])
        path = key_path.split('.')
        current_obj = target_obj
        
        # 마지막 전까지 객체 타고 들어가기
        for p in path[:-1]:
            current_obj = getattr(current_obj, p)
        
        # 마지막 속성 이름
        prop_name = path[-1]
        
        # 속성이 실제로 있는지 확인 후 설정
        if hasattr(current_obj, prop_name):
            # Blender 5.x: ImageFormatSettings.file_format은 media_type 선세팅 필요
            if prop_name == "file_format" and hasattr(current_obj, "file_format"):
                set_output_image_format(current_obj, value, label=f"{key_path}: ")
            else:
                # 데이터 타입 자동 변환 (블렌더가 웬만하면 알아서 처리함)
                setattr(current_obj, prop_name, value)
            # print(f"  [OK] {key_path} = {value}") # 디버깅용
        else:
            print(f"  [SKIP] 존재하지 않는 속성: {prop_name} (in {key_path})")
            
    except Exception as e:
        print(f"  [FAIL] 설정 실패: {key_path} = {value} ({e})")

def load_project_render_settings(context):
    scene = context.scene
    
    # 1. JSON 파일 경로 찾기 (기존 함수 get_project_paths 사용)
    base_path = get_project_paths() # 예: T:\
    
    # 경로가 없으면 중단
    if not base_path:
        print("[WARN] 프로젝트 경로를 찾을 수 없습니다.")
        return False

    json_path = os.path.join(base_path, "_json", "renderSetting.json")
    
    if not os.path.exists(json_path):
        print(f"[WARN] 렌더 세팅 파일 없음: {json_path}")
        return False

    print(f"[Build] JSON 세팅 로드: {json_path}")

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] JSON 파싱 에러: {e}")
        return False

    # -------------------------------------------------------
    # [핵심] 반복문으로 자동 매핑
    # -------------------------------------------------------
    
    mapping = {
        "view_settings": scene.view_settings,
        "eevee_settings": scene.eevee,
        "render_settings": scene.render,
    }

    for section_name, target_obj in mapping.items():
        if section_name in data:
            for key, value in data[section_name].items():
                if section_name == "eevee_settings" and scene.render.engine != 'BLENDER_EEVEE':
                    continue
                
                # 스마트 설정 함수 호출
                set_nested_property(target_obj, key, value)

    # -------------------------------------------------------
    # 특수 로직들
    # -------------------------------------------------------

    # 1. View Layers (없으면 자동 생성)
    if "view_layer_settings" in data:
        for vl_name, is_enabled in data["view_layer_settings"].items():
            vl = scene.view_layers.get(vl_name)
            if not vl:
                vl = scene.view_layers.new(name=vl_name)
            vl.use = is_enabled

    # 2. Compositor Nodes
    if data.get("use_compositor") and "nodes" in data:
        scene.render.use_compositing = False
        set_scene_compositor_enabled(scene, False)
        # tree = scene.node_tree
        
        # for node_data in data["nodes"]:
            # if node_data["type"] == "CompositorNodeRLayers":
                # layer_name = node_data.get("layer_name")
                
                # if layer_name and layer_name not in scene.view_layers:
                    # scene.view_layers.new(name=layer_name)

                # node = None
                # for n in tree.nodes:
                    # if n.type == 'R_LAYERS' and n.layer == layer_name:
                        # node = n
                        # break
                
                # if not node:
                    # node = tree.nodes.new('CompositorNodeRLayers')
                    # node.layer = layer_name
                
                # if "location" in node_data:
                    # node.location = node_data["location"]
                # if "mute" in node_data:
                    # node.mute = node_data["mute"]

    # 3. 기타 (🔥 여기서 200%로 튀던 버그 완벽 차단 🔥)
    if "resolution_scale" in data:
        # 기존: scene.render.resolution_percentage = int(data["resolution_scale"] * 100)
        scene.render.resolution_percentage = 100
    else:
        scene.render.resolution_percentage = 100

    if data.get("linkClass", False):
        pass

    print("[Build] 렌더 세팅 적용 완료.")
    return True


def get_base_filepath(scene):
    """지정된 씬 번호와 컷 번호를 사용하여 기본 파일 경로를 반환합니다."""
    my_tool = scene.my_tool
    scene_number = my_tool.scene_number
    cut_number = my_tool.cut_number
    base_path1 = get_project_paths()
    base_path = os.path.join(base_path1, "output", "ren", scene_number, f"{scene_number}_{cut_number}")
    default_version = "v001"

    # 해당 경로에 있는 모든 버전 넘버 찾기
    if os.path.exists(base_path):
        versions = [int(re.search(r"v(\d{3})", item).group(1)) for item in os.listdir(base_path) if re.search(r"v(\d{3})", item)]
        
        # 가장 높은 버전 넘버 찾기
        if versions:
            latest_version = max(versions)
            default_version = f"v{str(latest_version + 1).zfill(3)}"

    # os.path.join을 사용하여 original_path를 구성합니다.
    original_path = os.path.join(base_path, default_version, f"{scene_number}_{cut_number}_")

    # os.path.join을 사용하여 new_path를 구성합니다.
    new_path = os.path.join(base_path, default_version)

    return original_path, new_path, default_version


def find_collection_in_view_layer(collection_name, view_layer):
    """
    뷰 레이어에서 지정된 이름의 컬렉션을 찾아 반환합니다.
    """
    for layer_coll in view_layer.layer_collection.children:
        if layer_coll.collection.name == collection_name:
            return layer_coll

def apply_collection_properties_recursive(layer_collection, property_name, property_value):
    """
    재귀적으로 컬렉션과 하위 컬렉션에 속성을 적용합니다.
    """
    setattr(layer_collection, property_name, property_value)
    for child in layer_collection.children:
        apply_collection_properties_recursive(child, property_name, property_value)

def set_layer_collection_properties(layer_collection, holdout=False, indirect_only=False, exclude=False):
    layer_collection.holdout = holdout
    layer_collection.indirect_only = indirect_only
    layer_collection.exclude = exclude

def toggle_collection_properties(collection, property_name):
    """컬렉션의 속성을 토글합니다."""
    setattr(collection, property_name, not getattr(collection, property_name))

def set_and_restore_view_layer_properties(context, scene, view_layer, collection, properties):
    """
    뷰 레이어와 컬렉션의 속성을 설정하고 복원합니다.

    :param context: Blender 컨텍스트
    :param scene: 현재 씬
    :param view_layer: 대상 뷰 레이어 이름
    :param collection: 대상 컬렉션 이름
    :param properties: {"exclude": bool, "holdout": bool, "indirect_only": bool} 형태의 딕셔너리
    """
    # 1. 현재 뷰 레이어 저장
    current_view_layer = context.window.view_layer

    # 2. 대상 뷰 레이어로 변경
    target_view_layer_obj = scene.view_layers[view_layer]
    # print(f"Changing view layer to: {view_layer}")
    context.window.view_layer = target_view_layer_obj

    # 3. 현재 엑티브된 뷰 레이어 출력
    # print(f"Current active view layer: {context.window.view_layer.name}")

    # 4. 컬렉션 속성 설정 전 디버깅 메시지
    # print(f"Before applying properties - Target collection: {collection}")

    # 5. 컬렉션 속성 설정
    target_col = find_collection_in_view_layer(collection, target_view_layer_obj)
    if target_col:
        # 속성 설정
        for prop_name, prop_value in properties.items():
            setattr(target_col, prop_name, prop_value)
    else:
        print(f"Collection not found: {collection}")

    # 6. 컬렉션 속성 설정 후 디버깅 메시지
    # print(f"After applying properties - Target collection: {collection}")

    # 7. 원래의 뷰 레이어로 복원
    # print(f"Restoring view layer to: {current_view_layer.name}")
    context.window.view_layer = current_view_layer
    
def get_project_settings_path():
    # 프로젝트 설정에 따라 경로 가져오기
    base_path = get_project_paths()
    settings_path = os.path.join(base_path, "_json", "renderSetting.json")
    return settings_path

def load_settings():
    settings_path = get_project_settings_path()
    try:
        with open(settings_path, 'r', encoding='utf-8') as file: # encoding 추가 권장
            return json.load(file)
    except FileNotFoundError:
        # self.report는 Operator 클래스 안에서만 쓸 수 있습니다.
        # 여기서는 콘솔에 출력하는 것으로 대체합니다.
        print(f"[ERROR] 설정 파일을 찾을 수 없습니다: {settings_path}")
        return {}
    except json.JSONDecodeError:
        print(f"[ERROR] 설정 파일 형식이 잘못되었습니다: {settings_path}")
        return {}
    except Exception as e:
        print(f"[ERROR] 설정 로드 중 알 수 없는 오류: {e}")
        return {}

def _disable_default_view_layer(scene):
    """기본 ViewLayer를 철저하게 렌더에서 제외"""
    vl = scene.view_layers.get("ViewLayer")
    if vl:
        vl.use = False
        print("[SF] 기본 ViewLayer 렌더 OFF 완료")
    else:
        print("[SF][WARN] 기본 ViewLayer를 찾을 수 없습니다.")


class SF_OT_ViewLayerSetupOperator(bpy.types.Operator):
    """뷰 레이어 생성 및 세팅"""
    bl_idname = "sf.view_layer_setup"
    bl_label = "View Layer Setup"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        # --- ViewLayer 기본 설정 ---
        if "ViewLayer" in scene.view_layers:
            scene.view_layers["ViewLayer"].use_pass_cryptomatte_material = True
            scene.view_layers["ViewLayer"].use_pass_cryptomatte_object = True
            scene.view_layers["ViewLayer"].use_pass_z = True

        # --- ch_vl ---
        if "ch_vl" not in scene.view_layers:
            scene.view_layers.new(name="ch_vl")
        set_and_restore_view_layer_properties(context, scene, "ch_vl", "ch_col", {"exclude": False, "holdout": False, "indirect_only": False})
        set_and_restore_view_layer_properties(context, scene, "ch_vl", "ch_blocker_col", {"exclude": False, "holdout": True, "indirect_only": False})
        set_and_restore_view_layer_properties(context, scene, "ch_vl", "bg_col", {"exclude": True, "holdout": True, "indirect_only": True})
        set_and_restore_view_layer_properties(context, scene, "ch_vl", "prop_col", {"exclude": True, "holdout": True, "indirect_only": True})
        scene.view_layers["ch_vl"].use_pass_cryptomatte_material = True
        scene.view_layers["ch_vl"].use_pass_cryptomatte_asset = True
        scene.view_layers["ch_vl"].use_pass_cryptomatte_object = True
        scene.view_layers["ch_vl"].use_pass_z = True

        # --- bg_vl ---
        if "bg_vl" not in scene.view_layers:
            scene.view_layers.new(name="bg_vl")
        set_and_restore_view_layer_properties(context, scene, "bg_vl", "ch_col", {"exclude": True, "holdout": False, "indirect_only": True})
        set_and_restore_view_layer_properties(context, scene, "bg_vl", "ch_blocker_col", {"exclude": True, "holdout": False, "indirect_only": False})
        set_and_restore_view_layer_properties(context, scene, "bg_vl", "bg_col", {"exclude": False, "holdout": False, "indirect_only": False})
        set_and_restore_view_layer_properties(context, scene, "bg_vl", "prop_col", {"exclude": False, "holdout": False, "indirect_only": False})
        scene.view_layers["bg_vl"].use_pass_cryptomatte_material = True
        scene.view_layers["bg_vl"].use_pass_cryptomatte_object = True
        scene.view_layers["bg_vl"].use_pass_z = True

        # --- lightmask_vl ---
        if "lightmask_vl" not in scene.view_layers:
            scene.view_layers.new(name="lightmask_vl")
        set_and_restore_view_layer_properties(context, scene, "lightmask_vl", "lightmask_col", {"exclude": False, "holdout": False, "indirect_only": False})
        set_and_restore_view_layer_properties(context, scene, "lightmask_vl", "ch_col", {"exclude": True, "holdout": True, "indirect_only": True})
        set_and_restore_view_layer_properties(context, scene, "lightmask_vl", "ch_blocker_col", {"exclude": True, "holdout": True, "indirect_only": True})
        set_and_restore_view_layer_properties(context, scene, "lightmask_vl", "bg_col", {"exclude": True, "holdout": True, "indirect_only": True})
        set_and_restore_view_layer_properties(context, scene, "lightmask_vl", "prop_col", {"exclude": True, "holdout": True, "indirect_only": True})
        scene.view_layers["lightmask_vl"].use_pass_cryptomatte_material = False
        scene.view_layers["lightmask_vl"].use_pass_z = True

        # 기본 ViewLayer로 되돌리기
        bpy.context.window.view_layer = bpy.context.scene.view_layers["ViewLayer"]
        self.report({'INFO'}, "View layers created and configured.")
        # 기본 ViewLayer 비활성화 🔥 (중요 포인트)
        _disable_default_view_layer(scene)
        
        return {'FINISHED'}



class SF_OT_BuildSceneOperator(bpy.types.Operator):
    bl_idname = "sf.build_scene_operator"
    bl_label = "Build Scene"

    def execute(self, context):
        my_tool = context.scene.my_tool
        scene = context.scene
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        project_prefix = get_project_prefix()
        scene.name = f"{project_prefix}_{scene_number}_{cut_number}"
        
        # "Collection" 컬렉션과 그 하위 컬렉션 삭제
        if "Collection" in bpy.data.collections:
            for col in bpy.data.collections["Collection"].children:
                bpy.data.collections.remove(col)
            bpy.data.collections.remove(bpy.data.collections["Collection"])

        # 카메라 불러오기
        bpy.ops.sf.import_scene_camera()

        # 카테고리 컬렉션 생성
        categories = ["ch", "ch_blocker", "prop", "bg", "lightmask"]
        for category in categories:
            category_name = f"{category}_col"
            if category_name not in scene.collection.children:
                new_col = bpy.data.collections.new(category_name)
                scene.collection.children.link(new_col)

        # 뷰포트 셰이딩 옵션
        if context.space_data.type == 'VIEW_3D':
            context.space_data.shading.show_backface_culling = True
        else:
            print("This operation is only valid in the 3D View.")
            
        set_scene_compositor_enabled(context.scene, True, create_tree=False)
        
        # 🔥 아웃라이너 필터 켜기 (블렌더 4.x 호환 및 에러 방어)
        try:
            outliner_area = next(a for a in bpy.context.screen.areas if a.type == "OUTLINER")
            space = outliner_area.spaces
            
            outliner_attrs = [
                "show_restrict_column_enable",
                "show_restrict_column_select",
                "show_restrict_column_hide",
                "show_restrict_column_viewport",
                "show_restrict_column_render",
                "show_restrict_column_holdout",
                "show_restrict_column_indirect_only"
            ]
            for attr in outliner_attrs:
                if hasattr(space, attr):
                    setattr(space, attr, True)
        except StopIteration:
            pass

        # 렌더링 파일 경로 설정
        values = get_base_filepath(scene)
        original_path, new_path = values[:2]    
        bpy.ops.sf.generate_operator()
        bpy.ops.sf.version_operator(increment=-999)
        
        settings = self.load_settings()
        if settings:
            self.apply_settings(settings)
        else:
            return {'CANCELLED'}

        # 🔥 레졸루션 처리 로직 (1/2 사이즈 인식 및 뻥튀기)
        base_path = get_project_paths()
        json_file_name = f"{project_prefix}_{scene_number}_{cut_number}_camera_data.json"
        full_json_path = os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache", json_file_name)

        camera_data = {}
        if os.path.exists(full_json_path):
            with open(full_json_path, 'r') as json_file:
                camera_data = json.load(json_file)

        json_w = camera_data.get('resolutionX')
        json_h = camera_data.get('resolutionY')

        if json_w and json_h:
            # 마야에서 1/2 사이즈로 넘어왔을 경우
            if json_w < 2500:
                final_w = int(json_w * 2)
                final_h = int(json_h * 2)
                print(f"[INFO] 1/2 사이즈 카메라 감지됨. 해상도 2배 업스케일: {final_w}x{final_h}")
            else:
                final_w = int(json_w)
                final_h = int(json_h)
        else:
            if project_prefix == "DSC":
                final_w, final_h = 4096, 1716
            elif project_prefix == "ttm":
                final_w, final_h = 3840, 1634
            else:
                final_w, final_h = 1920, 1080
            print(f"[WARN] JSON 해상도 데이터 없음. 프로젝트 기본 해상도 강제 적용: {final_w}x{final_h}")

        # 렌더링 코덱 오류(H.264 등) 방지를 위한 홀수 픽셀 짝수화 보정
        if final_h % 2 != 0:
            final_h += 1
        if final_w % 2 != 0:
            final_w += 1

        scene.render.resolution_x = final_w
        scene.render.resolution_y = final_h

        # ✅ 기본 ViewLayer 렌더링 끄기
        if "ViewLayer" in scene.view_layers:
            default_vl = scene.view_layers["ViewLayer"]
            default_vl.use = False
            print("[INFO] 기본 ViewLayer 렌더링 비활성화")

        sc = scene
        set_output_exr_multilayer(sc.render.image_settings, label="Scene Build: ")

        # JSON 렌더 세팅 불러오기 (여기서 예전에는 200%로 덮어썼음)
        load_project_render_settings(context)       
        
        # 🔥 [최종 쐐기] load_project_render_settings 이후에도 무조건 100% 강제 고정!
        scene.render.resolution_percentage = 100

        self.report({'INFO'}, "Scene Build Complete (Settings & Resolution Loaded)")

        return {'FINISHED'}

    def get_project_settings_path(self):
        base_path = get_project_paths()
        settings_path = os.path.join(base_path, "_json", "renderSetting.json")
        return settings_path

    def load_settings(self):
        settings_path = self.get_project_settings_path()
        try:
            with open(settings_path, 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            self.report({'ERROR'}, "설정 파일을 찾을 수 없습니다.")
            return {}
        except json.JSONDecodeError:
            self.report({'ERROR'}, "설정 파일 형식이 잘못되었습니다.")
            return {}

    def clear_all_nodes(self, node_tree):
        for node in node_tree.nodes:
            node_tree.nodes.remove(node)

    def add_render_layer_node(self, node_tree, layer_name, location):
        render_layer_node = node_tree.nodes.new(type='CompositorNodeRLayers')
        render_layer_node.layer = layer_name
        render_layer_node.location = location

    def apply_settings(self, settings):
        scene = bpy.context.scene
        eevee = scene.eevee
        cycles = scene.cycles
        render = scene.render
        tree = get_scene_compositor_tree(scene, create=False)
        viewLayer = scene.view_layers

        # 렌더 설정 적용
        render_settings = settings.get("render_settings", {})
        for setting, value in render_settings.items():
            try:
                set_nested_property(render, setting, value)
            except (AttributeError, TypeError, ValueError) as e:
                print(f"Render 설정 적용 중 오류 발생: {setting} = {value} - {e}")
                continue

        # 뷰 레이어 설정 적용
        view_layer_settings = settings.get("view_layer_settings", {})
        for layer_name, use in view_layer_settings.items():
            if layer_name in scene.view_layers:
                scene.view_layers[layer_name].use = use
            else:
                print(f"뷰 레이어 '{layer_name}'를 찾을 수 없습니다.")

        scene.unit_settings.length_unit = 'CENTIMETERS'

        # Eevee 설정 적용
        eevee_settings = settings.get("eevee_settings", {})
        for setting, value in eevee_settings.items():
            try:
                setattr(eevee, setting, value)
            except (AttributeError, TypeError, ValueError) as e:
                continue

        # Cycles 설정 적용
        cycles_settings = settings.get("cycles_settings", {})
        for setting, value in cycles_settings.items():
            try:
                setattr(cycles, setting, value)
            except (AttributeError, TypeError, ValueError) as e:
                continue

        # 추가 Cycles 설정
        try:
            cycles.device = 'GPU'
            cycles.preview_adaptive_threshold = 1
            cycles.preview_samples = 16
            cycles.adaptive_threshold = 0.5
            cycles.samples = 30
            cycles.use_preview_denoising = True
            cycles.preview_denoiser = 'OPTIX'
            cycles.denoiser = 'OPTIX'
            cycles.use_denoising = True
            cycles.sampling_pattern = 'BLUE_NOISE'
            cycles.transparent_max_bounces = 50
            cycles.volume_bounces = 1
            cycles.transmission_bounces = 8
            cycles.diffuse_bounces = 1
            cycles.glossy_bounces = 5
            cycles.sample_clamp_direct = 0
            cycles.sample_clamp_indirect = 1
            cycles.texture_limit = '1024'
            cycles.texture_limit_render = '2048'
            cycles.caustics_reflective = False
            cycles.caustics_refractive = False
            cycles.use_fast_gi = True
            cycles.fast_gi_method = 'REPLACE'

            if scene.world and scene.world.light_settings:
                scene.world.light_settings.ao_factor = 0
                scene.world.light_settings.distance = 0.1

            render.use_simplify = True
            render.simplify_subdivision_render = 2
            render.simplify_subdivision = 0
            render.film_transparent = True
        except (AttributeError, TypeError, ValueError) as e:
            print(f"Cycles 추가 설정 적용 중 오류 발생: {e}")

        # View Transform 설정
        engine = scene.render.engine
        if engine in {"BLENDER_EEVEE_GOO", "BLENDER_WORKBENCH_GOO"}:
            scene.view_settings.view_transform = "Standard"
        else:
            try:
                parts = scene.name.split("_")
                sn = int(parts[1]) if len(parts) > 1 else int(getattr(bpy.context.scene.my_tool, "scene_number", 0))
            except Exception:
                sn = int(getattr(bpy.context.scene.my_tool, "scene_number", 0))

            if sn == 10:
                scene.view_settings.view_transform = "Filmic"
            elif sn == 20:
                scene.view_settings.view_transform = "Standard"
            elif sn >= 30:
                if "Khronos PBR Neutral" in bpy.context.scene.display_settings.display_device or True:
                    try:
                        scene.view_settings.view_transform = "Khronos PBR Neutral"
                    except TypeError:
                        scene.view_settings.view_transform = "Standard"

    # def apply_compositor_settings(self, settings):
        # tree = bpy.context.scene.node_tree
        # if settings.get('use_compositor', None) is True:
            # bpy.context.scene.use_nodes = True
            # bpy.context.scene.render.use_compositing = False

            # # self.setup_nodes(tree, settings)
        # elif settings.get('use_compositor', None) is False:
            # bpy.context.scene.use_nodes = True
            # bpy.context.scene.render.use_compositing = False

        # # if not tree:
            # # # bpy.context.scene.use_nodes = True
            # # tree = bpy.context.scene.node_tree

        # # 기존 노드들을 제거합니다
        # for node in tree.nodes:
            # tree.nodes.remove(node)

        # # JSON 파일에 정의된 노드 설정을 기반으로 노드를 추가합니다
        # for node_info in settings.get('nodes', []):
            # add_render_layer_node(tree, node_info['layer_name'], tuple(node_info['location']), node_info.get('mute', False))

        
################################################################
#########################Scnene Check ##########################
################################################################
# [cleanup] duplicate update/get_scene helpers removed.

class SF_OT_GenerateOperator(bpy.types.Operator):
    """Cache 폴더에서 USD를 읽어와 어셋 리스트를 생성"""
    bl_idname = "sf.generate_operator"
    bl_label = "Generate from Cache"

    def execute(self, context):
        scene = context.scene
        project_prefix = get_project_prefix()
        
        # 1. 씬/컷 번호 가져오기
        scene_number = scene.my_tool.scene_number
        cut_number = scene.my_tool.cut_number

        # 2. 프로젝트별 올바른 경로 가져오기 (이 부분이 핵심 수정 사항)
        # 기존: get_usd_path()가 S드라이브를 강제하던 문제 해결
        base_path = get_project_paths()  # 예: "T:\" for THE_TRAP
        if not base_path:
            self.report({'ERROR'}, "Project Path를 찾을 수 없습니다. Project 설정을 확인하세요.")
            return {'CANCELLED'}

        # 3. 실제 캐시 디렉토리 구성
        # 경로: T:\scenes\0010\0010\ren\cache
        cache_dir = os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache")

        if not os.path.exists(cache_dir):
            self.report({'WARNING'}, f"Cache 폴더가 없습니다: {cache_dir}")
            # 폴더가 없으면 리스트를 비우고 종료
            scene.sf_file_categories.clear()
            return {'CANCELLED'}

        found_assets = {}

        # 4. 파일 스캔 시작
        try:
            files = os.listdir(cache_dir)
        except Exception as e:
            self.report({'ERROR'}, f"폴더 읽기 실패: {e}")
            return {'CANCELLED'}

        for file in files:
            # 확장자가 .usd 인지 확인
            if not file.endswith(".usd"):
                continue
                
            # 파일명 분해: prefix_scene_cut_category_assetname.usd
            # 예: ttm_0010_0010_ch_hero.usd
            parts = file.split('_')
            
            # 최소한의 길이 체크 (prefix, scene, cut, category, name... 5개 이상)
            # 그리고 현재 프로젝트 접두사(ttm 등)와 일치하는지 확인
            if len(parts) >= 5 and parts[0] == project_prefix:
                
                # 카테고리 (ch, bg, prop 등) - 4번째 요소 (인덱스 3)
                category_name = parts[3]

                # 어셋 이름 추출 (chage_1 등 언더바 포함 이름 대응)
                asset_name = '_'.join(parts[4:]).replace('.usd', '')

                # 딕셔너리에 수집
                if category_name not in found_assets:
                    found_assets[category_name] = []

                if asset_name not in found_assets[category_name]:
                    found_assets[category_name].append(asset_name)

        # 5. UI 리스트 갱신
        scene.sf_file_categories.clear()
        
        # 카테고리 이름순 정렬하여 UI 생성
        for category_name in sorted(found_assets.keys()):
            category = scene.sf_file_categories.add()
            category.name = category_name
            
            # 어셋 이름순 정렬
            for item_name in sorted(found_assets[category_name]):
                new_item = category.items.add()
                new_item.name = item_name
                new_item.is_selected = False

        total_count = sum(len(v) for v in found_assets.values())
        
        if total_count == 0:
            self.report({'WARNING'}, f"폴더는 찾았으나 매칭되는 USD 파일이 없습니다.\n경로: {cache_dir}\n접두사: {project_prefix}")
        else:
            self.report({'INFO'}, f"총 {total_count}개 어셋 로드됨 (Path: {base_path})")
            
        return {'FINISHED'}


bpy.types.Scene.sf_scene_number = bpy.props.StringProperty(
    name="Scene Number",
    default=""
)

bpy.types.Scene.sf_cut_number = bpy.props.StringProperty(
    name="Cut Number",
    default=""
)



        
################################################################
#########################Link Operation#########################
################################################################

class SF_OT_LinkSelectedOperator(bpy.types.Operator):
    bl_idname = "sf.link_selected_operator"
    bl_label = "Link Selected"

    def execute(self, context):
        my_tool = context.scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        bpy.context.window.view_layer = bpy.context.scene.view_layers["ViewLayer"]
        selected_assets = [item.name for category in context.scene.sf_file_categories for item in category.items if item.is_selected]
        for asset_name in selected_assets:
            self.link_asset(asset_name, context, scene_number, cut_number)

        return {'FINISHED'}

    def link_asset(self, asset_name, context, scene_number, cut_number):
        cache_file_path = self.get_cache_file_path(asset_name, scene_number, cut_number, context)

        # USD 파일 임포트 및 생성된 오브젝트 삭제
        self.import_and_remove_usd(cache_file_path)

        # 어셋의 컬렉션 내의 모든 메쉬에 대해 작업 수행
        asset_col = bpy.data.collections.get(f"{asset_name}_col")
        if asset_col:
            category_name = self.get_category_name(asset_name)
            for obj in asset_col.objects:
                if obj.type == 'MESH':
                    self.apply_cache_to_mesh(obj, asset_name, scene_number, cut_number, category_name)

    def get_cache_file_path(self, asset_name, scene_number, cut_number, context):
        scene = context.scene
        base_path = get_project_paths()
        category_name = self.get_category_name(asset_name)
        project_prefix = get_project_prefix()  # 현재 프로젝트의 식별자를 얻습니다.
        cache_file_format = f"{project_prefix}_{scene_number}_{cut_number}_{category_name}_{asset_name}.usd"

        return os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache", cache_file_format)


    def import_and_remove_usd(self, file_path):
        # USD 파일 임포트
        bpy.ops.wm.usd_import(filepath=file_path, relative_path=True, import_meshes=False, import_subdiv=False, set_frame_range=False)
        # 임포트된 모든 객체를 확인
        imported_objects = bpy.context.selected_objects

        # 메시 캐시가 아닌 객체들을 식별하여 삭제
        for obj in imported_objects:
            if not self.is_mesh_cache_object(obj):
                bpy.data.objects.remove(obj, do_unlink=True)

    def is_mesh_cache_object(self, obj):
        # 객체가 메시 캐시를 포함하는지 확인
        for mod in obj.modifiers:
            if mod.type == 'MESH_SEQUENCE_CACHE':
                return True
        return False

    def find_full_object_path(self, obj):
        path = obj.name.split('.')[0]
        current_obj = obj

        while current_obj.parent:
            current_obj = current_obj.parent
            # 모든 이름에서 '.001', '.002' 등을 제거
            current_obj_name = current_obj.name.split('.')[0]
            path = f"{current_obj_name}/{path}"

        return f"/{path}"



    def apply_cache_to_mesh(self, obj, asset_name, scene_number, cut_number, category_name):
        prefix = get_project_prefix()
        project = bpy.context.scene.my_project_settings.projects

        usd_filename = f"{prefix}_{scene_number}_{cut_number}_{category_name}_{asset_name}.usd"
        usd_path = get_usd_path(scene_number, cut_number, asset_name, project, category_name)

        # 오브젝트에 기존 MeshSequenceCache 모디파이어만 갱신
        msc = None
        for mod in obj.modifiers:
            if mod.type == 'MESH_SEQUENCE_CACHE':
                msc = mod
                break

        if not msc:
            print(f"[SKIP] {obj.name}: MeshSequenceCache 모디파이어가 없어 경로만 갱신하지 못함")
            return

        if not msc.cache_file:
            print(f"[SKIP] {obj.name}: 기존 cache_file 데이터블록이 없어 경로만 갱신하지 못함")
            return

        msc.cache_file.name = usd_filename
        msc.cache_file.filepath = usd_path
        msc.read_data = {'VERT', 'UV', 'COLOR'}


        

        
    def get_category_name(self, asset_name):
        # 동적으로 이름 목록을 가져오기
        character_names = get_character_names()
        bg_names = get_bg_names()
        prop_names = get_prop_names()

        # 기존 카테고리 결정 로직
        if asset_name in character_names:
            return "ch"
        elif asset_name in bg_names:
            return "bg"
        elif asset_name in prop_names:
            return "prop"
        else:
            return "prop"





# 캐시 파일 링킹에 사용되는 공통 코드
def link_cache_files(context, scene_number, cut_number, selected_only=False):
    scene = context.scene
    project_prefix = get_project_prefix()  # 현재 프로젝트의 식별자를 얻습니다.
    cache_file_format = f"//cache\\{project_prefix}_{{}}_{{}}_"  # 예: 프로젝트 식별자_0010_0010_
    scene_number = my_tool.scene_number
    cut_number = my_tool.cut_number

    for category in context.scene.sf_file_categories:
        for item in category.items:
            if item.is_selected or not selected_only:
                cache_file_name = f"{item.name}.usd"
                cache_file_path = cache_file_format.format(scene_number, cut_number) + cache_file_name

                if os.path.exists(cache_file_path):
                    # 캐시 파일이 존재하는 경우, 파일을 연결합니다.
                    bpy.data.cache_files[cache_file_name].filepath = cache_file_path
                else:
                    context.report({'WARNING'}, f"Cache file not found: {cache_file_name}")
                    
class SF_OT_LinkCharacterLights1(bpy.types.Operator):
    bl_idname = "object.sf_link_character_lights1"
    bl_label = "Link Character Lights"
    bl_options = {'REGISTER', 'UNDO'}                    

    def execute(self, context):
        filepath1 = bpy.context.blend_data.filepath
        asset_name = os.path.splitext(os.path.basename(filepath1))[0].split("_")[0]
        target_collection_name = f"{asset_name}_light_col"
        
        # 지정된 이름을 가진 컬렉션을 찾습니다.
        target_collection = bpy.data.collections.get(target_collection_name)
        
        if target_collection:
           
            # 컬렉션 내의 모든 라이트 오브젝트를 찾아 라이트 그룹을 적용합니다.
            for obj in target_collection.objects:
                
                if obj.type == 'LIGHT':
                    
                    # 라이트의 라이트 그룹 설정을 조정합니다.
                    obj.data.light_groups.use_default = False  # 기본 라이트 그룹 사용 비활성화
                    
                    # 기존의 모든 라이트 그룹을 삭제합니다.
                    obj.data.light_groups.groups.clear()
                    
                    # 새로운 라이트 그룹을 추가합니다.
                    new_group = obj.data.light_groups.groups.add()
                    new_group.name = f"{asset_name}_lgt"  # 라이트 그룹 이름 변경
                else:
                    print(f"오브젝트 '{obj.name}'는 라이트가 아닙니다.")
        else:
            print(f"컬렉션 '{target_collection_name}'를 찾을 수 없습니다.")
            
        return {'FINISHED'}
        
class SF_OT_LinkAllOperator(bpy.types.Operator):
    bl_idname = "sf.link_all_operator"
    bl_label = "Link All"

    def execute(self, context):
        my_tool = context.scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number

        link_cache_files(context, scene_number, cut_number, selected_only=False)
        return {'FINISHED'}

################################################################
#########################Import Operation#######################
################################################################
       
       
## 이 스크립트는 씬에 있는 모든 메터리얼의 이름에서 네임스페이스와 서피스를 제거한 후 임시 메모리에 저장합니다.
## USD로 불러온 메터리얼은 네임스페이스를 떼고, MIA_를 MA_로 변환합니다.
## USD메터리얼을 씬 안의 메터리얼과 매칭해 같은 이름의 메터리얼로 교체합니다.
## 다시말해 USD로 불러온 메터리얼을 씬의 메터리얼로 교체하는 스크립트 입니다.

def replace_usd_materials_with_existing(asset_name: str):
    """선택된 오브젝트들 중 MESH에 대해 기존 material로 교체"""

    for obj in bpy.context.selected_objects:
        if obj.type != 'MESH':
            continue

        for i, slot in enumerate(obj.material_slots):
            mat = slot.material
            if not mat:
                continue

            mat_name = mat.name.replace("MIA_", "MI_").replace(":", "_").replace(".", "_")
            existing_mat = bpy.data.materials.get(mat_name)

            if existing_mat and existing_mat != mat:
                print(f"[MaterialSwitch] {obj.name} : {mat.name} → {existing_mat.name}")
                obj.material_slots[i].material = existing_mat

def sanitize_material_name(raw_name):
    """
    MIA/네임스페이스/버전 등 불필요한 부분 제거하고 MI_ 접두어로 정제된 메터리얼 이름 반환
    예: 'FenceRoadE01:MIA_FenceRoadE1.001' → 'MI_FenceRoadE1'
    """
    name = raw_name

    if 'MIA_' in name:
        name = 'MIA_' + name.split('MIA_')[-1]
    name = name.replace("MIA_", "MI_")

    if ':' in name:
        name = name.split(':')[-1]
    if '.' in name:
        name = '.'.join(name.split('.')[:-1])

    return name


def apply_matching_materials(obj):
    materials = bpy.data.materials
    non_matching_materials = []

    # 씬 내 메터리얼들을 정제된 이름으로 맵핑
    processed_materials = {}
    for mat in materials:
        processed_name = sanitize_material_name(mat.name)
        processed_materials[processed_name] = mat

    for slot in obj.material_slots:
        sanitized_name = sanitize_material_name(slot.name)

        if sanitized_name in processed_materials:
            slot.material = processed_materials[sanitized_name]
        else:
            if slot.material is not None:
                old_name = slot.material.name
                try:
                    slot.material.name = sanitized_name
                    print(f"[Material Rename] {old_name} → {sanitized_name}")
                except Exception as e:
                    print(f"[Error] Failed to rename {old_name} → {sanitized_name}: {e}")
            else:
                print(f"[Warning] No material in slot '{slot.name}' (object: {obj.name})")

            non_matching_materials.append(sanitized_name)

    if non_matching_materials:
        print("No matching materials found for:")
        for mat_name in non_matching_materials:
            print(f"- {mat_name}")

            
            
def add_render_layer_node(tree, layer_name, location, mute=False):
    # 현재 활성 씬을 사용
    current_scene = bpy.context.scene
    base_path = get_project_paths()
    render_layer_node = None
    for node in tree.nodes:
        if isinstance(node, bpy.types.CompositorNodeRLayers) and node.layer == layer_name:
            render_layer_node = node
            break
    
    if not render_layer_node:
        render_layer_node = tree.nodes.new(type='CompositorNodeRLayers')
        render_layer_node.location = location
        render_layer_node.layer = layer_name
        render_layer_node.scene = current_scene  # 현재 씬을 노드의 씬으로 지정

    # 렌더 레이어 노드 활성화/비활성화 설정
    render_layer_node.mute = mute
    
    # 파일 출력 노드 생성 및 연결
    output_node = tree.nodes.new(type='CompositorNodeOutputFile')
    output_node.location = (500, location[1])  # 옆에 위치
    output_node.mute = mute  # 출력 노드도 동일하게 mute 설정
    
    # 렌더링 파일 경로 설정
    values = get_base_filepath(current_scene)
    _, new_path, _ = values
    output_node.base_path = new_path  # 경로 설정
    
    # 파일 포맷 및 컬러 설정
    set_output_png(output_node.format, alpha=True, label=f"FileOutput {layer_name}: ")
    
    # 파일 서브패스 설정
    my_tool = current_scene.my_tool  # 현재 씬의 사용자 정의 속성 사용
    scene_number = my_tool.scene_number  # 씬 번호
    cut_number = my_tool.cut_number  # 컷 번호
    output_node.file_slots[0].path = f"{scene_number}_{cut_number}_{layer_name}_"
    tree.links.new(render_layer_node.outputs['Image'], output_node.inputs[0])


def add_kuwa_layer_node(tree, layer_name, location):
    current_scene = bpy.context.scene
    base_path, new_path, _ = get_base_filepath(current_scene)  # new_path 초기화

    # 렌더 레이어 노드 찾기 또는 생성
    render_layer_node = None
    for node in tree.nodes:
        if isinstance(node, bpy.types.CompositorNodeRLayers) and node.layer == layer_name:
            render_layer_node = node  # 이미 존재하는 노드 찾기
            break

    if render_layer_node is None:
        render_layer_node = tree.nodes.new(type='CompositorNodeRLayers')
        render_layer_node.location = location
        render_layer_node.layer = layer_name
        render_layer_node.scene = current_scene

    # Kuwahara 필터 노드 생성 및 연결
    kuwahara_node = None
    for node in tree.nodes:
        if isinstance(node, bpy.types.CompositorNodeKuwahara) and node.inputs[0].is_linked:
            if node.inputs[0].links[0].from_node == render_layer_node:
                kuwahara_node = node  # 이미 존재하는 Kuwahara 노드 찾기
                break

    if kuwahara_node is None:
        kuwahara_node = tree.nodes.new(type='CompositorNodeKuwahara')
        kuwahara_node.location = (300, location[1])
        # kuwahara_node.size = 8
        kuwahara_node.inputs[1].default_value = 8
        kuwahara_node.use_high_precision = True

        
        
        tree.links.new(render_layer_node.outputs['Image'], kuwahara_node.inputs[0])



    # 파일 출력 노드 생성 및 연결
    output_node = None
    output_path_suffix = f"{layer_name}_kuwa_"
    for node in tree.nodes:
        if isinstance(node, bpy.types.CompositorNodeOutputFile):
            if node.file_slots[0].path.endswith(output_path_suffix):
                output_node = node  # 이미 존재하는 파일 출력 노드 찾기
                break

    if output_node is None:
        output_node = tree.nodes.new(type='CompositorNodeOutputFile')
        output_node.location = (500, location[1])
        output_node.base_path = new_path  # 경로 설정
        set_output_png(output_node.format, alpha=True, label=f"FileOutput {layer_name}: ")
        my_tool = current_scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        output_node.file_slots[0].path = f"{scene_number}_{cut_number}_{output_path_suffix}"
        tree.links.new(kuwahara_node.outputs['Image'], output_node.inputs[0])





def add_layer_node(tree, layer_name, location, node_type='RLayers', post_process_type=None, settings=None):
    current_scene = bpy.context.scene
    _, new_path, _ = get_base_filepath(current_scene)

    # Find or create the render layer node
    layer_node = None
    for node in tree.nodes:
        if isinstance(node, bpy.types.CompositorNodeRLayers) and node.layer == layer_name:
            layer_node = node
            break

    if layer_node is None:
        layer_node = tree.nodes.new(type='CompositorNodeRLayers')
        layer_node.location = location
        layer_node.layer = layer_name
        layer_node.scene = current_scene

    # Additional node processing
    if post_process_type:
        process_node = tree.nodes.new(type=post_process_type)
        process_node.location = (location[0] + 300, location[1])

        if settings:
            for key, value in settings.items():
                if hasattr(process_node.format, key):  # Check if the key is an attribute of the format object
                    if key == "file_format":
                        set_output_image_format(process_node.format, value, label=f"FileOutput {layer_name}: ")
                    else:
                        setattr(process_node.format, key, value)
                elif key not in ['subpath_suffix']:  # Ignore special keys that are handled separately
                    setattr(process_node, key, value)

        if post_process_type == 'CompositorNodeOutputFile':
            process_node.base_path = new_path
            scene_number = current_scene.my_tool.scene_number
            cut_number = current_scene.my_tool.cut_number
            subpath = settings.get('subpath_suffix', '')  # Retrieve the subpath suffix if provided
            # Apply the customized file path to the file slot
            process_node.file_slots[0].path = f"{scene_number}_{cut_number}_{layer_name}_{subpath}"

        tree.links.new(layer_node.outputs['Image'], process_node.inputs[0])

class SF_OT_LinkRimToNode1(bpy.types.Operator):
    bl_idname = "object.link_rim_to_node1"
    bl_label = "Link Rim to Node"

    def execute(self, context):
        selected_characters = [item.name for category in context.scene.sf_file_categories for item in category.items if item.is_selected]

        for asset_name in selected_characters:
            light_obj_name = f"{asset_name}_light"
            light_obj = bpy.data.objects.get(light_obj_name)

            if not light_obj:
                self.report({'WARNING'}, f"{light_obj_name} object not found, skipping...")
                continue

            # rim01과 rim02 오브젝트를 모두 찾음
            rim_objects = []
            for child in light_obj.children:
                if "rim01" in child.name or "rim02" in child.name:
                    rim_objects.append(child)

            if not rim_objects:
                self.report({'WARNING'}, f"No rim01 or rim02 objects found under {light_obj_name}, skipping...")
                continue

            for rim_object in rim_objects:
                if rim_object.users > 0 and (rim_object.library is None or rim_object.library is not None):
                    for material in bpy.data.materials:
                        if material.use_nodes and material.name.startswith(f"MI_{asset_name}_"):
                            nodes = material.node_tree.nodes
                            links = material.node_tree.links

                            for node in nodes:
                                if node.type == 'GROUP' and node.node_tree and node.node_tree.name.startswith('SF_Toon_Logic'):
                                    input_index = 53 if "rim01" in rim_object.name else 54
                                    if 0 <= input_index < len(node.inputs):
                                        input_socket = node.inputs[input_index]
                                        existing_links = list(input_socket.links)
                                        for link in existing_links:
                                            links.remove(link)

                                        # 텍스처 코디네이트 노드 생성 및 링크
                                        tc_node = nodes.new(type='ShaderNodeTexCoord')
                                        tc_node.object = rim_object
                                        links.new(tc_node.outputs['Object'], input_socket)

                                        print(f"성공: {rim_object.name}에 대한 텍스처 코디네이트 노드가 생성되고 연결되었습니다.")
                                    else:
                                        print(f"실패: 입력 인덱스 '{input_index}'가 범위를 벗어났습니다.")

                            self.remove_unused_nodes_from_material(material)

        return {'FINISHED'}
        
    def remove_unused_nodes_from_material(self, material):
        if material.use_nodes:
            nodes = material.node_tree.nodes
            links = material.node_tree.links

            # Collect all 'Texture Coordinate' nodes that are not connected to any other nodes
            unused_tex_coord_nodes = [
                node for node in nodes
                if node.type == 'TEX_COORD' and not any(link.from_node == node or link.to_node == node for link in links)
            ]

            # Delete all unused 'Texture Coordinate' nodes
            for node in unused_tex_coord_nodes:
                nodes.remove(node)

class LinkClass(bpy.types.Operator):
    bl_idname = "sf.link_class"
    bl_label = "Link Collection"

    def execute(self, context):
        scene = context.scene
        if scene.get('ch_processed'):
            # 'ch' 카테고리가 이미 처리되었다면 관련 로직을 건너뛰기
            return {'FINISHED'}
        my_tool = context.scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        ch_scene = bpy.context.scene
        
        settings = load_settings()     
        link_class = settings.get('linkClass', False)
        
        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    asset_name = item.name
                    blend_file_path = self.get_blend_file_path(asset_name, category.name, scene_number, cut_number)
                    self.append_materials_and_collection_from_blend(context, blend_file_path, asset_name, category.name)
                    asset_col_name = f"{asset_name}_col"

                    if link_class:
                        if category.name == 'ch':
                            self.add_solidify_to_collection_objects(blend_file_path, asset_col_name)
                            self.update_mesh_data_from_blend(blend_file_path, asset_col_name)
                            self.add_properties_and_link(asset_name)  # 새로 추가한 기능
                            bpy.ops.sf.updatelightposition_class()
        return {'FINISHED'}

    def add_properties_and_link(self, asset_name):
        # bpy.ops.object.sf_add_properties_and_link1()
        # asset_name이 유효한지 확인 (빈 문자열이 아닌지)
        if not asset_name or not asset_name.strip():
            self.report({'ERROR'}, "Asset name is invalid or empty.")
            return

        try:
            # 필요한 데이터가 유효하다면 연산자 호출
            bpy.ops.object.sf_add_properties_and_link1()
        except RuntimeError as e:
            # 오류 발생 시 적절한 에러 메시지를 출력
            self.report({'ERROR'}, f"Error occurred: {str(e)}")



    def remove_existing_properties(self, obj):
        for prop_name in list(obj.keys()):
            del obj[prop_name]

    def add_custom_properties(self, obj, properties_info):
        for prop_name, default, prop_type, _, min_val, max_val, soft_min, soft_max in properties_info:
            obj[prop_name] = default
            # 프로퍼티 매니저 업데이트 보장
            obj.id_properties_ensure()
            property_manager = obj.id_properties_ui(prop_name)
            if prop_type == "COLOR":
                property_manager.update(min=min_val, max=max_val, soft_min=soft_min, soft_max=soft_max, subtype='COLOR', default=default)
            elif prop_type == "FLOAT":
                property_manager.update(min=min_val, max=max_val, soft_min=soft_min, soft_max=soft_max, subtype='NONE', default=default)

    def get_blend_file_path(self, asset_name, category_name, scene_number, cut_number):
        base_path = get_project_paths()
        return os.path.join(base_path, "assets", category_name, asset_name, "mod", f"{asset_name}.blend")


    def append_materials_and_collection_from_blend(self, context, blend_file_path, asset_name, category_name):
        light_col_name = f"{asset_name}_light_col"
        light_obj_name = f"{asset_name}_light"

        # 현재 씬에서 해당 이름의 컬렉션이나 Empty 오브젝트가 이미 존재하는지 확인
        existing_collection = bpy.data.collections.get(light_col_name)
        existing_empty = bpy.data.objects.get(light_obj_name)

        # 이미 존재한다면 로드 및 링크 프로세스를 스킵
        if existing_collection or (existing_empty and existing_empty.type == 'EMPTY'):
            print(f"{light_col_name} or {light_obj_name} already exists. Skipping load.")
            return

        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
                    # data_to.materials = data_from.materials
                    data_to.worlds = data_from.worlds
                    if category_name in ['bg', 'ch', 'prop']:  # 'bg'와 'ch' 두 경우를 모두 처리
                        light_col_name = f"{asset_name}_light_col"
                        if light_col_name in data_from.collections:
                            data_to.collections = [light_col_name]

                        # 직접 링크 방식을 사용하여 컬렉션을 현재 레이어에 링크
                        self.link_collection_to_active_layer(context, light_col_name)

        # 'bg' 또는 'ch' 카테고리에 따라 적절한 상위 컬렉션에 링크
        if category_name in ['bg', 'ch', 'prop']:
            target_col_name = f"{category_name}_col"  # 'bg_col' 또는 'ch_col'
            target_col = bpy.context.scene.collection.children.get(target_col_name)
            if target_col:
                for col in data_to.collections:
                    target_col.children.link(col)


    def link_collection_to_active_layer(self, context, collection_name):
        # 현재 활성 뷰 레이어를 가져옴
        active_layer = context.view_layer

        # 링크하려는 컬렉션을 찾음
        collection = bpy.data.collections.get(collection_name)

        # 컬렉션이 존재하고 아직 링크되지 않았다면 링크
        if collection and collection_name not in context.scene.collection.children:
            active_layer.active_layer_collection.collection.children.link(collection)
            print(f"{collection_name} collection linked to the active layer.")
                
    def add_solidify_to_collection_objects(self, blend_file_path, target_collection_name):
        print(f"Starting process for blend file: {blend_file_path} and target collection: {target_collection_name}")
        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
            data_to.objects = [name for name in data_from.objects]
            print(f"Objects loaded from blend file: {len(data_to.objects)}")

        target_collection = bpy.data.collections.get(target_collection_name)
        if not target_collection:
            print(f"Collection '{target_collection_name}' not found.")
            return
        else:
            print(f"Found target collection '{target_collection_name}' with {len(target_collection.objects)} objects.")

        for obj in target_collection.objects:
            if obj.type == 'MESH':
                # print(f"Processing object: {obj.name}")
                base_name = obj.name.split('.')[0]
                blend_obj = next((o for o in data_to.objects if o.name.split('.')[0] == base_name), None)

                if blend_obj and any(mod.name.startswith('LBS') for mod in blend_obj.modifiers):
                    print(f"'LBS' modifier found on blend object: {blend_obj.name}")
                    
                    # 'Solidify' 모디파이어 추가 및 설정
                    solidify_modifier = obj.modifiers.get("Solidify")
                    if not solidify_modifier:
                        print(f"Adding 'Solidify' modifier to object: {obj.name}")
                        solidify_modifier = obj.modifiers.new(name="Solidify", type='SOLIDIFY')
                    solidify_modifier.thickness = 0.1
                    solidify_modifier.offset = 1
                    solidify_modifier.use_flip_normals = True

                    # 버텍스 그룹 설정
                    vg_name = "LBS Solidify Outline"
                    if vg_name in obj.vertex_groups:
                        print(f"Vertex group '{vg_name}' found in object: {obj.name}")
                        solidify_modifier.vertex_group = vg_name
                    else:
                        print(f"Vertex group '{vg_name}' not found in object: {obj.name}, attempting to create.")
                        vg = obj.vertex_groups.new(name=vg_name)
                        solidify_modifier.vertex_group = vg.name

                    solidify_modifier.invert_vertex_group = True
                    solidify_modifier.use_quality_normals = True
                    solidify_modifier.thickness_clamp = 5
                    solidify_modifier.material_offset = -10
                    print(f"'Solidify' modifier added and configured for '{obj.name}'.")
                    
                    # 여기서 'LBS' 머티리얼이 이미 존재하는지 확인
                    if any(mat.name.startswith('LBS') for mat in obj.data.materials):
                        print(f"'LBS' material already exists on {obj.name}, skipping to next object.")
                        continue  # 이미 'LBS' 머티리얼이 존재하면, 다음 오브젝트로 넘어갑니다.

                    # 'LBS' 머티리얼 적용 로직
                    if blend_obj.material_slots:
                        lbs_material = blend_obj.material_slots[0].material
                        if lbs_material:
                            print(f"Found 'LBS' material: {lbs_material.name} for object: {obj.name}")
                            # 기존 머티리얼 인덱스 저장
                            original_mat_indices = [poly.material_index for poly in obj.data.polygons]
                            # 기존 머티리얼 저장
                            original_materials = [mat for mat in obj.data.materials]
                            # 'LBS' 머티리얼 추가
                            print(f"Applying 'LBS' material: {lbs_material.name} to object: {obj.name}")
                            obj.data.materials.clear()
                            obj.data.materials.append(lbs_material)
                            # 기존 머티리얼을 다시 추가
                            for mat in original_materials:
                                obj.data.materials.append(mat)
                            # 폴리곤에 대한 머티리얼 인덱스 업데이트
                            for poly, original_index in zip(obj.data.polygons, original_mat_indices):
                                poly.material_index = min(original_index + 1, len(obj.data.materials)-1)



    def update_mesh_data_from_blend(self, blend_file_path, asset_col_name):
        try:
            with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
                data_to.objects = data_from.objects
                if not data_to.objects: 
                    raise ValueError(f"No objects were loaded from the blend file: {blend_file_path}")
            print(f"Loading blend file from: {blend_file_path}")
        except ValueError as e:
            print(e)  
        except OSError as e:
            print(f"Failed to open blend file: {e}")  
        except RuntimeError as e:
            print(f"Failed to load blend file: {e}")  
        else:
            print(f"Target mesh name to find: {asset_col_name}")
            target_collection = bpy.data.collections.get(asset_col_name)
            if target_collection:
                for obj in target_collection.objects:
                    if obj.type == 'MESH':
                        matching_object = next((o for o in data_to.objects if o.name.split('.')[0] == obj.name.split('.')[0]), None)
                        if matching_object and matching_object.type == 'MESH':
                            # Vertex groups transfer
                            obj.vertex_groups.clear()
                            for vg in matching_object.vertex_groups:
                                new_vg = obj.vertex_groups.new(name=vg.name)
                                for vert_index in range(len(matching_object.data.vertices)):
                                    try:
                                        weight = vg.weight(vert_index)
                                        new_vg.add([vert_index], weight, 'REPLACE')
                                    except RuntimeError:
                                        # Ignore vertices that are not in the group
                                        pass
                            print(f"Transferred vertex groups for object: {obj.name}")
                            
                            # Mask modifier transfer
                            for mod in matching_object.modifiers:
                                if mod.type == 'MASK':
                                    # 새로운 Mask 모디파이어 추가
                                    new_mod = obj.modifiers.new(name=mod.name, type='MASK')
                                    
                                    # 기존 모디파이어의 속성 복사
                                    new_mod.vertex_group = mod.vertex_group
                                    new_mod.invert_vertex_group = mod.invert_vertex_group
                                    new_mod.show_viewport = mod.show_viewport
                                    new_mod.show_render = mod.show_render
                                    
                                    print(f"Transferred 'Mask' modifier from {matching_object.name} to {obj.name}")
                        else:
                            print(f"No matching object in blend file for: {obj.name}")

            else:
                print(f"Collection '{asset_col_name}' not found in the current scene.")
            return {'FINISHED'}

        return {'CANCELLED'}
        
class SF_OT_CopyDropletGeneratorOperator(bpy.types.Operator):
    """Copy Droplet Generator Modifiers, Geometry Nodes, and Material"""
    bl_idname = "sf.copy_droplet_generator"
    bl_label = "Copy Droplet Generator Modifier"

    def execute(self, context):
        scene = context.scene
        if scene.get('ch_processed'):
            return {'FINISHED'}
        
        my_tool = context.scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        ch_scene = bpy.context.scene
        
        settings = load_settings()     
        link_class = settings.get('linkClass', False)
        
        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    asset_name = item.name
                    blend_file_path = self.get_blend_file_path(asset_name, category.name, scene_number, cut_number)
                    self.append_materials_and_collection_from_blend(context, blend_file_path, asset_name, category.name)
                    asset_col_name = f"{asset_name}_col"

                    if link_class:
                        if category.name == 'ch':
                            self.copy_droplets_modifiers(blend_file_path, asset_col_name)
                            self.copy_droplet_generator_geometry_nodes(blend_file_path, asset_col_name)
                            self.copy_droplet_material(asset_col_name)
                            bpy.ops.sf.updatelightposition_class()

                            # 🔥 Droplets 중복 제거 로직 추가
                            target_collection = bpy.data.collections.get(asset_col_name)
                            if target_collection:
                                for obj in target_collection.objects:
                                    if obj.type == 'MESH':
                                        self.clean_duplicate_droplets_modifiers(obj)  # 🔥 추가된 클리너
        return {'FINISHED'}

    def get_blend_file_path(self, asset_name, category_name, scene_number, cut_number):
        base_path = get_project_paths()
        return os.path.join(base_path, "assets", category_name, asset_name, "mod", f"{asset_name}.blend")

    def append_materials_and_collection_from_blend(self, context, blend_file_path, asset_name, category_name):
        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
            data_to.worlds = data_from.worlds
            if category_name in ['bg', 'ch', 'prop']:
                light_col_name = f"{asset_name}_light_col"
                if light_col_name in data_from.collections:
                    data_to.collections = [light_col_name]
                self.link_collection_to_active_layer(context, light_col_name)

    def link_collection_to_active_layer(self, context, collection_name):
        active_layer = context.view_layer
        collection = bpy.data.collections.get(collection_name)
        if collection and collection_name not in context.scene.collection.children:
            active_layer.active_layer_collection.collection.children.link(collection)

    def copy_droplets_modifiers(self, blend_file_path, target_collection_name):
        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
            data_to.objects = data_from.objects

        target_collection = bpy.data.collections.get(target_collection_name)
        if not target_collection:
            self.report({'WARNING'}, f"Collection '{target_collection_name}' not found.")
            return
        
        for obj in target_collection.objects:
            if obj.type == 'MESH':
                # ✅ 중복 방지: Droplets 모디파이어가 이미 있으면 추가하지 않음
                if self.modifier_exists(obj, 'Droplets'):
                    print(f"⚠️ Skipping {obj.name} because Droplets modifier already exists.")
                    continue

                matching_object = next((o for o in data_to.objects if o.name.split('.')[0] == obj.name.split('.')[0]), None)
                if matching_object:
                    for mod in matching_object.modifiers:
                        if mod.name.startswith('Droplets'):
                            new_mod = obj.modifiers.new(name=mod.name, type=mod.type)
                            self.copy_modifier_properties(mod, new_mod)
                            self.copy_droplet_modifier_inputs(mod, new_mod)


    def copy_modifier_properties(self, source_mod, target_mod):
        for prop in source_mod.rna_type.properties:
            if prop.is_readonly:
                continue

            attr_name = prop.identifier
            try:
                source_value = getattr(source_mod, attr_name)
                setattr(target_mod, attr_name, source_value)
            except AttributeError:
                print(f"❌ AttributeError: {attr_name} cannot be copied from {source_mod.name}")
            except Exception as e:
                print(f"❌ Failed to copy attribute '{attr_name}' from {source_mod.name} to {target_mod.name}: {e}")

    def copy_droplet_modifier_inputs(self, source_mod, target_mod):
        input_values = {}
        
        for i in range(50):
            input_name = f"Input_{i}"
            try:
                if input_name in source_mod:
                    input_values[input_name] = source_mod[input_name]
            except KeyError:
                continue

        for input_name, input_value in input_values.items():
            try:
                if input_name in target_mod:
                    target_mod[input_name] = input_value
            except KeyError:
                print(f"❌ KeyError: {input_name} not found in {target_mod.name}")
            except Exception as e:
                print(f"❌ Failed to copy input '{input_name}' from {source_mod.name} to {target_mod.name}: {e}")

    def copy_droplet_generator_geometry_nodes(self, blend_file_path, target_collection_name):
        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
            data_to.objects = data_from.objects

        target_collection = bpy.data.collections.get(target_collection_name)
        if not target_collection:
            self.report({'WARNING'}, f"Collection '{target_collection_name}' not found.")
            return
        
        for obj in target_collection.objects:
            if obj.type == 'MESH':
                if any(mod.name.startswith('DropletGenerator') for mod in obj.modifiers):
                    print(f"⚠️ Skipping {obj.name} because DropletGenerator modifier already exists.")
                    continue
                
                matching_object = next((o for o in data_to.objects if o.name.split('.')[0] == obj.name.split('.')[0]), None)
                if matching_object:
                    for mod in matching_object.modifiers:
                        if mod.type == 'NODES' and mod.node_group and mod.node_group.name.startswith('DropletGenerator'):
                            new_mod = obj.modifiers.new(name=mod.name, type='NODES')
                            new_mod.node_group = mod.node_group

    def copy_droplet_material(self, asset_col_name):
        target_collection = bpy.data.collections.get(asset_col_name)
        if not target_collection:
            self.report({'WARNING'}, f"Collection '{asset_col_name}' not found.")
            return
        
        droplet_material = bpy.data.materials.get("DropletMat")
        if not droplet_material:
            self.report({'WARNING'}, "DropletMat material not found.")
            return
        
        for obj in target_collection.objects:
            if obj.type == 'MESH':
                material_names = [mat.name for mat in obj.data.materials if mat]
                if droplet_material.name not in material_names:
                    obj.data.materials.append(droplet_material)

    def modifier_exists(self, obj, modifier_name):
        """ 🔥 Droplets 모디파이어가 이미 존재하는지 확인 """
        for mod in obj.modifiers:
            if mod.name == modifier_name and mod.type == 'NODES':
                print(f"✅ {obj.name}에 이미 {modifier_name} 모디파이어가 존재합니다.")
                return True
        return False

    def clean_duplicate_droplets_modifiers(self, obj):
        """ 🔥 Droplets.001, Droplets.002와 같은 중복 모디파이어 삭제 """
        droplet_modifiers = [mod for mod in obj.modifiers if mod.name.startswith('Droplets')]
        
        # Droplets 이름의 모디파이어 중 첫 번째만 남기고 나머지는 삭제
        if len(droplet_modifiers) > 1:
            print(f"🗑️ Cleaning up duplicate Droplets modifiers on {obj.name}")
            for mod in droplet_modifiers[1:]:  # 첫 번째(Droplets) 제외하고 모두 삭제
                print(f"🗑️ Removing duplicate Droplets modifier: {mod.name} from {obj.name}")
                obj.modifiers.remove(mod)

                    
class SF_OT_RemoveDropletGeneratorOperator(bpy.types.Operator):
    """Remove Droplet Generator Modifiers, Geometry Nodes, and Material"""
    bl_idname = "sf.remove_droplet_generator"
    bl_label = "Remove Droplet Generator Modifier"

    def execute(self, context):
        scene = context.scene
        if not scene:
            self.report({'ERROR'}, "Scene not found.")
            return {'CANCELLED'}
        
        my_tool = context.scene.my_tool
        
        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    asset_name = item.name
                    asset_col_name = f"{asset_name}_col"
                    
                    self.remove_droplets_modifiers(asset_col_name)
                    self.remove_droplet_generator_geometry_nodes(asset_col_name)
                    self.remove_droplet_material(asset_col_name)
        
        return {'FINISHED'}

    def remove_droplets_modifiers(self, asset_col_name):
        """Remove Droplets modifiers from objects in the target collection."""
        target_collection = bpy.data.collections.get(asset_col_name)
        if not target_collection:
            self.report({'WARNING'}, f"Collection '{asset_col_name}' not found.")
            return
        
        for obj in target_collection.objects:
            if obj.type == 'MESH':
                modifiers_to_remove = [mod for mod in obj.modifiers if mod.name.startswith('Droplets')]
                for mod in modifiers_to_remove:
                    mod_name = mod.name  # 🔥 모디파이어 이름을 먼저 저장
                    obj.modifiers.remove(mod)  # 🗑️ 모디파이어 삭제
                    print(f"🗑 Removed Droplets modifier: {mod_name} from {obj.name}")  # 🔥 삭제 후에는 이름을 사용

    def remove_droplet_generator_geometry_nodes(self, asset_col_name):
        """Remove Droplet Generator Geometry Nodes modifiers."""
        target_collection = bpy.data.collections.get(asset_col_name)
        if not target_collection:
            self.report({'WARNING'}, f"Collection '{asset_col_name}' not found.")
            return
        
        for obj in target_collection.objects:
            if obj.type == 'MESH':
                modifiers_to_remove = [
                    mod for mod in obj.modifiers 
                    if mod.type == 'NODES' and mod.node_group.name.startswith('DropletGenerator')
                ]
                for mod in modifiers_to_remove:
                    mod_name = mod.name  # 🔥 모디파이어 이름을 먼저 저장
                    obj.modifiers.remove(mod)  # 🗑️ 모디파이어 삭제
                    print(f"🗑 Removed Geometry Nodes modifier: {mod_name} from {obj.name}")  # 🔥 삭제 후에는 이름을 사용

    def remove_droplet_material(self, asset_col_name):
        """Remove DropletMat material from objects in the target collection."""
        target_collection = bpy.data.collections.get(asset_col_name)
        if not target_collection:
            self.report({'WARNING'}, f"Collection '{asset_col_name}' not found.")
            return
        
        droplet_material = bpy.data.materials.get("DropletMat")
        if not droplet_material:
            self.report({'WARNING'}, "DropletMat material not found.")
            return
        
        for obj in target_collection.objects:
            if obj.type == 'MESH':
                material_names = [mat.name for mat in obj.data.materials if mat]  # 🔥 메터리얼 이름을 가져옵니다.
                if droplet_material.name in material_names:  # 🔥 이름으로 비교
                    index = obj.data.materials.find(droplet_material.name)
                    if index != -1:  # 🔥 올바른 인덱스를 찾았는지 확인
                        obj.data.materials.pop(index=index)  # 🗑️ 메터리얼 삭제 (키워드 인자 사용)
                        print(f"🗑 Removed DropletMat material from {obj.name}")
                        
                        
class UpdateLightPosition(bpy.types.Operator):
    bl_idname = "sf.updatelightposition_class"
    bl_label = "Update Light Position"
    
    def execute(self, context):
        scene = context.scene
        my_tool = context.scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        ch_scene = bpy.context.scene
        
        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    asset_name = item.name
                    asset_col_name = f"{asset_name}_col"                  
                    if category.name == 'ch':
                        self.update_light_position_based_on_meshes(asset_name)
        return {'FINISHED'}
        
    def update_light_position_based_on_meshes(self, asset_name):
        asset_col_name = f"{asset_name}_col"  # 어셋의 메인 컬렉션 이름
        asset_col = bpy.data.collections.get(asset_col_name)
        if not asset_col:
            print(f"{asset_col_name} 컬렉션을 찾을 수 없습니다.")
            return

        meshes = [obj for obj in asset_col.objects if obj.type == 'MESH']
        if not meshes:
            print(f"{asset_col_name} 내에 메쉬 객체가 없습니다.")
            return

        # 바운딩 박스의 모든 코너들을 월드 좌표로 계산
        world_corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]

        # 중심 위치 계산
        avg_loc = sum(world_corners, start=Vector((0,0,0))) / len(world_corners)
        
        # 가장 낮은 Z 위치 계산
        lowest_z = min(world_corners, key=lambda pt: pt.z).z

        light_obj_name = f"{asset_name}_light"
        light_obj = bpy.data.objects.get(light_obj_name)
        if not light_obj or light_obj.type != 'EMPTY':
            print(f"{light_obj_name} 이름의 Empty 오브젝트를 찾을 수 없습니다.")
            return

        # light_obj 오브젝트 위치를 업데이트 (X, Y는 중심 위치, Z는 가장 낮은 지점)
        light_obj.location.x = avg_loc.x
        light_obj.location.y = avg_loc.y
        light_obj.location.z = lowest_z
        print(f"{light_obj_name} 오브젝트 위치가 업데이트되었습니다. (X: {avg_loc.x}, Y: {avg_loc.y}, Z: {lowest_z})")


                   
class SubdivideClass(bpy.types.Operator):
    bl_idname = "sf.subdivide_class"
    bl_label = "Subdivide Mesh"

    def execute(self, context):
        scene = context.scene
        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:  # 사용자가 선택한 어셋만 고려
                    self.apply_subdivision_to_selected_assets(context)
        return {'FINISHED'}

    def apply_subdivision_to_selected_assets(self, context):
        for obj in bpy.data.objects:
            print(f"Checking object: {obj.name}, type: {obj.type}")
            if obj.type == 'MESH' and not obj.name.endswith('_ns_geo'):
                print(f"Applying subdivision to: {obj.name}")
                self.apply_subdivision(obj)
            elif obj.name.endswith('_ns_geo'):
                print(f"Subdivision not applied to: {obj.name} because it ends with '_ns_geo'")
            else:
                print(f"Subdivision not applied to: {obj.name} because it's not a mesh")

    def apply_subdivision(self, obj):
        if not any(mod.type == 'SUBSURF' for mod in obj.modifiers):
            mod = obj.modifiers.new(name="Subdivision", type='SUBSURF')
            mod.levels = 2  
            mod.render_levels = 2
            mod.boundary_smooth = 'PRESERVE_CORNERS'

            print(f"Subdivision applied to: {obj.name}")
        else:
            print(f"Subdivision not applied to: {obj.name} because it already has a subdivision modifier")        


class unSubdivideClass(bpy.types.Operator):
    bl_idname = "sf.unsubdivide_class"
    bl_label = "Un-Subdivide Mesh"

    def execute(self, context):
        self.remove_subdivision_from_all_assets()
        return {'FINISHED'}

    def remove_subdivision_from_all_assets(self):
        for obj in bpy.data.objects:
            print(f"Checking object: {obj.name}, type: {obj.type}")
            if obj.type == 'MESH' and not obj.name.endswith('_ns_geo'):
                print(f"Removing subdivision from: {obj.name}")
                self.remove_subdivision(obj)
            elif obj.name.endswith('_ns_geo'):
                print(f"Subdivision not removed from: {obj.name} because it ends with '_ns_geo'")
            else:
                print(f"Subdivision not removed from: {obj.name} because it's not a mesh")

    def remove_subdivision(self, obj):
        subsurf_modifiers = [mod for mod in obj.modifiers if mod.type == 'SUBSURF']
        if subsurf_modifiers:
            for mod in subsurf_modifiers:
                obj.modifiers.remove(mod)
                print(f"Subdivision removed from: {obj.name}")
        else:
            print(f"No subdivision modifier found on: {obj.name}")


class SF_OT_ClearCustomNormalOperator(bpy.types.Operator):
    bl_idname = "sf.clear_custom_normal_operator"
    bl_label = "Clear Custom Split Normals"
    
    def clear_custom_split_normals_and_disable_auto_smooth(self):
        # 원래 활성 오브젝트를 저장
        original_active = bpy.context.view_layer.objects.active

        # 현재 씬의 모든 오브젝트를 반복
        for obj in bpy.context.scene.objects:
            # 오브젝트 타입이 'MESH'인 경우에만 작업 수행
            if obj.type == 'MESH':
                # 해당 메시를 활성 오브젝트로 설정
                bpy.context.view_layer.objects.active = obj
                # 오브젝트를 선택 상태로 만듦
                obj.select_set(True)
                
                # 커스텀 스플릿 노멀 데이터 지우기
                bpy.ops.mesh.customdata_custom_splitnormals_clear()
                
                # 자동 스무딩 비활성화
                obj.data.use_auto_smooth = False
                
                # 다음 오브젝트를 위해 현재 오브젝트 선택 해제
                obj.select_set(False)

        # 원래 활성 오브젝트로 복원
        bpy.context.view_layer.objects.active = original_active

    def execute(self, context):
        self.clear_custom_split_normals_and_disable_auto_smooth()
        return {'FINISHED'}


import bpy

import bpy

class SF_OT_LinkLightProperties(bpy.types.Operator):
    """UI에서 선택한 어셋의 _light 속성을 
    _v03 노드에 드라이버로 연결"""
    bl_idname = "object.sf_link_light_properties"
    bl_label = "Link Light Properties"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        processed_assets = []

        for category in scene.sf_file_categories:
            for item in category.items:
                if not item.is_selected:
                    continue

                asset_name = item.name
                light_obj = bpy.data.objects.get(f"{asset_name}_light")
                collection = bpy.data.collections.get(f"{asset_name}_col")

                if not light_obj or not collection:
                    self.report({'WARNING'}, f"{asset_name}: light 또는 _col 컬렉션 없음, 스킵")
                    continue

                # 커스텀 프로퍼티 값 준비
                ambient_col = tuple(light_obj.get("P01_Ambient_Color", (1,1,1,1)))
                shadow_col  = tuple(light_obj.get("P02_Shadow_Color", (1,1,1,1)))
                ambient_val = float(ambient_col[0])
                line_val    = float(light_obj.get("P30_Line_Thickness", 0.1))

                # 컬렉션 하위 메쉬 순회
                for obj in collection.all_objects:
                    if obj.type != 'MESH':
                        continue
                    for slot in obj.material_slots:
                        mat = slot.material
                        if not mat or not mat.node_tree:
                            continue
                        for node in mat.node_tree.nodes:
                            # if node.type == "GROUP" and node.node_tree and node.node_tree.name == "SF_Toon_v03":
                            if node.type == 'GROUP' and node.node_tree and node.node_tree.name.startswith('SF_Toon_'):                                
                                self.apply_and_link(mat, node, light_obj, ambient_val, ambient_col, shadow_col, line_val)

                processed_assets.append(asset_name)

        if not processed_assets:
            self.report({'ERROR'}, "선택된 어셋 없음")
            return {'CANCELLED'}
        else:
            self.report({'INFO'}, f"{', '.join(processed_assets)} 처리 완료")
            return {'FINISHED'}

    # ---------------- 유틸 함수 ----------------
    def clear_links_and_drivers(self, mat, socket):
        if socket.is_linked:
            socket.links.clear()
        ad = mat.node_tree.animation_data
        if ad and ad.drivers:
            path = socket.path_from_id() + ".default_value"
            for fcurve in list(ad.drivers):
                if fcurve.data_path == path:
                    mat.node_tree.driver_remove(fcurve.data_path, fcurve.array_index)

    def add_driver(self, mat, socket, obj, prop_name, is_color=False):
        path = socket.path_from_id() + ".default_value"
        if is_color:
            for i in range(4):
                fcurve = mat.node_tree.driver_add(path, i)
                drv = fcurve.driver
                drv.type = 'AVERAGE'
                var = drv.variables.new()
                var.name = "var"
                var.targets[0].id = obj
                var.targets[0].data_path = f'["{prop_name}"][{i}]'
        else:
            fcurve = mat.node_tree.driver_add(path)
            drv = fcurve.driver
            drv.type = 'AVERAGE'
            var = drv.variables.new()
            var.name = "var"
            var.targets[0].id = obj
            var.targets[0].data_path = f'["{prop_name}"]'

    def apply_and_link(self, mat, node, light_obj, ambient_val, ambient_col, shadow_col, line_val):
        # --Ambient
        if "--Ambient" in node.inputs:
            s = node.inputs["--Ambient"]
            self.clear_links_and_drivers(mat, s)
            s.default_value = ambient_col
            self.add_driver(mat, s, light_obj, "P01_Ambient_Color", is_color=True)

        # --Shadow Multiply
        if "--Shadow Multiply" in node.inputs:
            s = node.inputs["--Shadow Multiply"]
            self.clear_links_and_drivers(mat, s)
            s.default_value = shadow_col
            self.add_driver(mat, s, light_obj, "P02_Shadow_Color", is_color=True)

        # Line Size(Overall)
        if "Line Size(Overall)" in node.inputs:
            s = node.inputs["Line Size(Overall)"]
            self.clear_links_and_drivers(mat, s)
            s.default_value = line_val
            self.add_driver(mat, s, light_obj, "P30_Line_Thickness", is_color=False)


class SF_OT_AddPropertiesAndLink1(bpy.types.Operator):
    bl_idname = "object.sf_add_properties_and_link1"
    bl_label = "Add Properties and Link to Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        my_tool = context.scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number

        success_count = 0
        linethickness_prop = "P30_Line_Thickness"
        properties_info = self.get_properties_info()
        if not properties_info:
            self.report({'ERROR'}, "Failed to load properties info.")
            return {'CANCELLED'}

        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    asset_name = item.name
                    collection_name = f"{asset_name}_col"
                    light_obj_name = f"{asset_name}_light"
                    light_obj = bpy.data.objects.get(light_obj_name)

                    if not light_obj:
                        self.report({'WARNING'}, f"{light_obj_name} object not found, skipping...")
                        continue

                    self.remove_existing_drivers(collection_name)
                    self.remove_existing_properties(light_obj)
                    self.add_custom_properties(light_obj, properties_info)
                    self.add_drivers_to_materials(collection_name, light_obj, properties_info)
                    parent_obj = bpy.data.objects.get(asset_name)
                    self.process_all_meshes(parent_obj, light_obj, linethickness_prop)
                    # self.link_rim_to_node(context, asset_name)
                    
                    #모든 메터리얼에 대한 'Texture Coordinate' 노드 제거
                    for mat in bpy.data.materials:
                        self.remove_unlinked_tex_coord_nodes(mat)
                    
                    success_count += 1

        if success_count == 0:
            self.report({'ERROR'}, "No valid characters found to process")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Processed {success_count} characters successfully.")
        return {'FINISHED'}

    def get_properties_info(self):
        file_path = 'T:/_json/get_properties_info.json'
        try:
            with open(file_path, 'r') as infile:
                return json.load(infile)
        except Exception as e:
            print(f"Error loading properties info from {file_path}: {e}")
            return []

    def remove_existing_drivers(self, collection_name):
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            print(f"Collection '{collection_name}' not found")
            return

        for obj in collection.objects:
            if obj.type == 'MESH' and obj.data.materials:
                for mat in obj.data.materials:
                    if mat.use_nodes and mat.node_tree and mat.node_tree.animation_data:
                        drivers_to_remove = []
                        for driver in mat.node_tree.animation_data.drivers:
                            drivers_to_remove.append(driver.data_path)  # Collecting drivers before removal

                        for driver_path in drivers_to_remove:
                            try:
                                mat.node_tree.driver_remove(driver_path)
                                print(f"Successfully removed driver at {driver_path}")
                            except Exception as e:
                                print(f"Failed to remove driver at {driver_path}: {e}")

    def remove_existing_properties(self, obj):
        for prop_name in list(obj.keys()):
            del obj[prop_name]

    def add_custom_properties(self, obj, properties_info):
        obj.id_properties_ensure()  # Ensure the property manager is updated
        for prop_info in properties_info:
            prop_name = prop_info['name']
            default = prop_info['default']
            prop_type = prop_info['type']
            min_val = prop_info.get('min', 0)  # Default values for min, max if not provided
            max_val = prop_info.get('max', 1)
            soft_min = prop_info.get('soft_min', min_val)  # Use min_val if soft_min is not provided
            soft_max = prop_info.get('soft_max', max_val)  # Use max_val if soft_max is not provided

            # Set default value and type directly on the object
            obj[prop_name] = default

            # Update the property manager settings
            property_manager = obj.id_properties_ui(prop_name)
            if prop_type == "COLOR":
                property_manager.update(min=min_val, max=max_val, soft_min=soft_min, soft_max=soft_max, subtype='COLOR')
            elif prop_type == "FLOAT":
                property_manager.update(min=min_val, max=max_val, soft_min=soft_min, soft_max=soft_max, subtype='NONE')

            # After updating property_manager, ensure the default value is set correctly, especially for COLOR type
            obj[prop_name] = default
            
    def add_drivers_to_materials(self, collection_name, light_obj, properties_info):
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            print(f"Collection '{collection_name}' not found")
            return

        for obj in collection.objects:
            if obj.type == 'MESH' and obj.data.materials:
                for mat in obj.data.materials:
                    if mat.use_nodes:
                        for node in mat.node_tree.nodes:
                            if node.type == 'GROUP' and node.node_tree and node.node_tree.name == "SF_Toon_Logic":
                                for prop_info in properties_info:
                                    prop_name = prop_info['name']
                                    default = prop_info['default']
                                    prop_type = prop_info['type']
                                    input_idx = prop_info['index']
                                    self.add_driver_to_material(mat, node, prop_name, default, prop_type, input_idx, light_obj)
                               

    def add_driver_to_material(self, mat, node, prop_name, default, prop_type, input_idx, light_obj):
        # 노드와 해당 인덱스의 입력이 유효한지 확인
        node_input = node.inputs[input_idx] if input_idx < len(node.inputs) else None
        if node_input:
            path = f'nodes["{node.name}"].inputs[{input_idx}].default_value'
            if prop_type == "COLOR":
                for idx in range(4):  # RGBA 채널에 대해
                    fcurve = mat.node_tree.driver_add(path, idx)
                    self.setup_driver(fcurve, light_obj, prop_name, idx)
            elif prop_type == "FLOAT":
                fcurve = mat.node_tree.driver_add(path)
                self.setup_driver([fcurve], light_obj, prop_name)
        else:
            print(f"Node '{node.name}' does not have an input at index {input_idx}")


    def setup_driver(self, fcurves, obj, prop_name, idx=None):
        if not isinstance(fcurves, list):
            fcurves = [fcurves]
        for fcurve in fcurves:
            driver = fcurve.driver
            driver.type = 'AVERAGE'
            var = driver.variables.new()
            var.targets[0].id = obj
            if idx is not None:
                var.targets[0].data_path = f'["{prop_name}"][{idx}]'
            else:
                var.targets[0].data_path = f'["{prop_name}"]'

    def add_driver_to_modifier_thickness(self, target_obj, modifier_name, driver_source, linethickness_prop):
        # 드라이버를 추가할 솔리디파이 모디파이어의 thickness 속성을 찾습니다.
        modifier = target_obj.modifiers.get(modifier_name)
        if modifier and modifier.type == 'SOLIDIFY':
            # 드라이버가 이미 존재하는지 확인하고, 있다면 제거합니다.
            if target_obj.animation_data and target_obj.animation_data.drivers:
                # 모든 드라이버를 순회합니다.
                for fcurve in target_obj.animation_data.drivers:
                    # 해당 모디파이어의 thickness 속성에 대한 드라이버를 찾습니다.
                    if fcurve.data_path == f'modifiers["{modifier_name}"].thickness':
                        # 해당 드라이버를 제거합니다.
                        target_obj.driver_remove(fcurve.data_path)

            # 드라이버 설정
            fcurve = target_obj.driver_add(f'modifiers["{modifier_name}"].thickness')
            driver = fcurve.driver
            driver.type = 'AVERAGE'

            var = driver.variables.new()
            var.name = 'var'
            var.targets[0].id = driver_source
            var.targets[0].data_path = f'["{linethickness_prop}"]'
        else:
            self.report({'WARNING'}, "Modifier not found or not a Solidify modifier.")


    def process_all_meshes(self, parent_obj, driver_source, linethickness_prop):
        # parent_obj 하위의 모든 오브젝트를 순회합니다.
        for obj in parent_obj.children:
            # 메쉬 타입의 오브젝트만 처리합니다.
            if obj.type == 'MESH':
                # 모든 솔리디파이 모디파이어에 대해 드라이버를 추가합니다.
                for modifier in obj.modifiers:
                    if modifier.type == 'SOLIDIFY':
                        self.add_driver_to_modifier_thickness(obj, modifier.name, driver_source, linethickness_prop)
            # 재귀적으로 하위 오브젝트 처리
            self.process_all_meshes(obj, driver_source, linethickness_prop)
            
    def find_active_rim_object(self, asset_name):
        # Find the parent Empty object
        parent_name = f"{asset_name}_light"
        parent_obj = bpy.data.objects.get(parent_name)
        if not parent_obj:
            print(f"Parent object '{parent_name}' not found.")
            return None

        # Check for active object among the children
        for child in parent_obj.children:
            if child.name.startswith(f"{asset_name}_rim") and child.select_get():
                return child

        print("No active rim object found under the specified parent.")
        return None

    def find_all_mesh_objects(self, collection, max_depth=10):
        """
        주어진 컬렉션과 하위 컬렉션에 포함된 모든 메쉬 오브젝트를 반환합니다.
        최대 탐색 깊이를 max_depth로 제한합니다.
        """
        mesh_objects = []

        def recurse_collection(col, depth):
            if depth > max_depth:
                return
            for obj in col.objects:
                if obj.type == 'MESH':
                    mesh_objects.append(obj)
            for sub_col in col.children:
                recurse_collection(sub_col, depth + 1)

        recurse_collection(collection, 0)
        return mesh_objects


    def link_rim_to_node(self, context, asset_name):
        print(f"시작: {asset_name}에 대한 림 오브젝트를 찾는 중...")

        # 활성 림 오브젝트 검색
        active_rim_obj = self.find_active_rim_object(asset_name)
        if not active_rim_obj:
            print("실패: 활성 림 오브젝트를 찾을 수 없습니다.")
            return
        else:
            print(f"성공: 활성 림 오브젝트 '{active_rim_obj.name}'를 찾았습니다.")

        # 재료 컬렉션 검색
        material_collection_name = f"{asset_name}_col"
        print(f"재료 컬렉션 '{material_collection_name}'를 검색 중...")
        material_collection = bpy.data.collections.get(material_collection_name)
        if not material_collection:
            print(f"실패: 재료 컬렉션 '{material_collection_name}'을 찾을 수 없습니다.")
            return
        else:
            print(f"성공: 재료 컬렉션 '{material_collection_name}'을 찾았습니다.")

        # 재료 컬렉션 내 모든 메쉬 오브젝트 가져오기
        all_mesh_objects = self.find_all_mesh_objects(material_collection, max_depth=10)
        print(f"성공: 재료 컬렉션 내 총 {len(all_mesh_objects)}개의 메쉬 오브젝트를 찾았습니다.")

        # 림 오브젝트와 재료 컬렉션의 메쉬 오브젝트들 연결
        for obj in all_mesh_objects:
            if obj.data.materials:
                for mat in obj.data.materials:
                    if mat.use_nodes:
                        nodes = mat.node_tree.nodes
                        links = mat.node_tree.links
                        print(f"노드 수정 중: 재료 '{mat.name}'...")
                        for node in nodes:
                            if node.type == 'GROUP' and node.node_tree and node.node_tree.name.startswith('SF_Toon_Logic'):
                                rim_name = active_rim_obj.name[len(asset_name)+1:]
                                input_index = 53 if "rim01" in rim_name else 54

                                if 0 <= input_index < len(node.inputs):
                                    input_socket = node.inputs[input_index]
                                    # 기존 링크 제거
                                    existing_links = list(input_socket.links)
                                    for link in existing_links:
                                        links.remove(link)

                                    # 새 텍스처 좌표 노드 생성 및 링크
                                    tc_node = nodes.new(type='ShaderNodeTexCoord')
                                    tc_node.object = active_rim_obj
                                    links.new(tc_node.outputs['Object'], input_socket)
                                    print(f"성공: '{rim_name}'에 대한 노드 연결 완료.")
                                else:
                                    print(f"실패: 입력 인덱스 '{input_index}'가 범위를 벗어났습니다.")
                    else:
                        print(f"노드 사용 안함: 재료 '{mat.name}'는 노드를 사용하지 않습니다.")
            else:
                print(f"오류: '{obj.name}' 오브젝트는 메터리얼이 없습니다.")



    def remove_unlinked_tex_coord_nodes(self, material):
        if material.node_tree:
            for node in material.node_tree.nodes:
                # 'Texture Coordinate' 노드이고, 어떤 출력도 연결되지 않은 경우
                if node.type == 'TEX_COORD' and not any(output.is_linked for output in node.outputs):
                    # 노드 삭제
                    material.node_tree.nodes.remove(node)

# (클래스 등록 목록 위에 추가)

class SF_OT_ImportModePopup(bpy.types.Operator):
    """'Append'와 'Link' 임포트 방식 중 하나를 선택하는 팝업 메뉴를 띄웁니다."""
    bl_idname = "sf.import_mode_popup"
    bl_label = "임포트 방식 선택"

    def execute(self, context):
        # 이 오퍼레이터는 메뉴만 띄우므로 직접 실행하는 로직은 없습니다.
        return {'FINISHED'}

    def invoke(self, context, event):
        # 팝업 메뉴를 그리는 함수를 정의합니다.
        def draw(self, context):
            layout = self.layout
            layout.label(text="어떤 방식으로 에셋을 가져올까요?")
            
            # 'Append (Legacy USD)' 버튼: 누르면 import_mode='APPEND'로 실행
            op_append = layout.operator("sf.import_selected_operator", text="Append (Legacy USD)", icon='APPEND_BLEND')
            op_append.import_mode = 'APPEND'

            # 'Link + Override' 버튼: 누르면 import_mode='LINK'로 실행
            op_link = layout.operator("sf.import_selected_operator", text="Link + Override", icon='LINK_BLEND')
            op_link.import_mode = 'LINK'

        # 정의한 draw 함수를 사용하여 팝업 메뉴를 화면에 표시
        context.window_manager.popup_menu(draw, title=self.bl_label, icon='QUESTION')
        return {'FINISHED'}
# 기존 SF_OT_ImportSelectedOperator 클래스를 아래 내용으로 전체 교체하세요.

class SF_OT_ImportSelectedOperator(bpy.types.Operator):
    bl_idname = "sf.import_selected_operator"
    bl_label = "Import Selected"
    bl_options = {'REGISTER', 'UNDO'}
    
    # 팝업에서 선택한 모드를 전달받기 위한 속성
    import_mode: bpy.props.EnumProperty(
        name="Import Mode",
        items=[('APPEND', "Append", "Original USD import method"),
               ('LINK', "Link", "Link collection and create override")],
        default='APPEND'
    )

    def execute(self, context):
        print(f"--- [SF Import] Start Mode: {self.import_mode} ---")
        
        scene = context.scene
        # 1. 선택된 아이템이 있는지 먼저 확인 (통합 체크)
        selected_items = []
        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    selected_items.append((category, item))

        if not selected_items:
            self.report({'WARNING'}, "선택된 어셋이 없습니다! (리스트의 체크박스를 확인하세요)")
            print("[SF Import] No items selected.")
            return {'CANCELLED'}

        # 2. 모드에 따라 실행
        try:
            if self.import_mode == 'LINK':
                self.execute_link_mode(context, selected_items)
            else: # APPEND 모드
                self.execute_append_mode(context, selected_items)
        except Exception as e:
            self.report({'ERROR'}, f"임포트 중 에러 발생: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        print("--- [SF Import] Finished ---")
        
        bpy.ops.sf.update_selected_operator_dsc()
        
        return {'FINISHED'}

    # -------------------------------------------------------------------
    # ▼ [모드 1] Append 방식
    # -------------------------------------------------------------------
    def execute_append_mode(self, context, selected_items):
        scene = context.scene
        base_path = get_project_paths()
        scene_num = scene.my_tool.scene_number
        cut_num = scene.my_tool.cut_number
        
        # 프로젝트 경로 체크
        if not base_path:
            self.report({'ERROR'}, "프로젝트 경로(Base Path)를 가져올 수 없습니다. Project 설정을 확인하세요.")
            return

        print(f"[SF Import] Base Path: {base_path}")

        # 선택된 아이템 순회
        for category, item in selected_items:
            # ch 카테고리는 Subdivision 적용 등 특수 로직이 있어서 구분
            is_ch = (category.name == "ch")
            self.process_selected_item_append(item, category, f"{category.name}_col", base_path, scene_num, cut_num, context, apply_subdivision=is_ch)

    def process_selected_item_append(self, item, category, category_col_name, base_path, scene_number, cut_number, context, apply_subdivision):
        import os
        asset_name = item.name
        asset_col_name = f"{asset_name}_col"
        
        # 캐시 디렉토리 경로 구성
        directory = os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache")
        
        # 디렉토리 존재 여부 확인
        if not os.path.exists(directory):
            self.report({'ERROR'}, f"Cache 폴더를 찾을 수 없습니다: {directory}")
            return

        # USD 파일 찾기
        asset_file_path = find_asset_file_path(directory, asset_name)

        if not asset_file_path:
            self.report({'WARNING'}, f"USD 파일을 찾을 수 없음: {asset_name} (in {directory})")
            return

        print(f"[SF Import] Found USD: {asset_file_path}")

        # 블렌드 파일(머티리얼용) 찾기 및 Append
        blend_file_path = self.get_blend_file_path(base_path, category.name, asset_name)
        if blend_file_path and os.path.exists(blend_file_path):
            self.append_materials_from_blend(blend_file_path, asset_name, category.name)
        else:
            print(f"[SF Import] Published Blend not found: {blend_file_path}")

        # USD 임포트 실행
        self.import_asset_from_usd(asset_file_path, category_col_name, asset_col_name, category.name, context) 
        
        # 후처리
        bpy.ops.sf.cleanup_orphans_combined1()
        
        if apply_subdivision: # 캐릭터인 경우
            self.apply_light_mask_to_collection(asset_col_name, context)
            self.apply_subdivision_to_meshes(asset_col_name)

    def append_materials_from_blend(self, blend_file_path, asset_name, category_name):
        try:
            with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
                data_to.materials = data_from.materials
            # 이름 정리 (MIA_ 등)
            for mat in data_to.materials:
                if mat and '.' in mat.name: 
                    mat.name = mat.name.split('.')[0]
        except OSError:
            print(f"[SF Import Warning] Failed to load library: {blend_file_path}")

    def import_asset_from_usd(self, asset_file_path, category_col_name, asset_col_name, category_name, context):
        # 컬렉션 구조 생성
        if category_col_name not in bpy.context.scene.collection.children:
            new_category_col = bpy.data.collections.new(category_col_name)
            bpy.context.scene.collection.children.link(new_category_col)
        category_col = bpy.context.scene.collection.children[category_col_name]

        if asset_col_name not in category_col.children:
            new_asset_col = bpy.data.collections.new(asset_col_name)
            category_col.children.link(new_asset_col)
        asset_col = category_col.children[asset_col_name]

        # USD 임포트
        # 활성 컬렉션 변경 (임포트될 위치)
        layer_col = context.view_layer.layer_collection
        target_layer_col = None
        
        # 재귀적으로 레이어 컬렉션 찾기
        def find_layer_col(lc, name):
            if lc.name == name: return lc
            for child in lc.children:
                res = find_layer_col(child, name)
                if res: return res
            return None

        cat_lc = find_layer_col(layer_col, category_col_name)
        if cat_lc:
            asset_lc = find_layer_col(cat_lc, asset_col_name)
            if asset_lc:
                context.view_layer.active_layer_collection = asset_lc

        # 실제 임포트 수행
        bpy.ops.wm.usd_import(filepath=asset_file_path, relative_path=True, import_subdiv=False, set_frame_range=False)
        
        # 임포트 후 스케일 조정 및 머티리얼 적용
        for obj in asset_col.objects:
            if obj.parent is None:
                # USD 임포트 시 스케일이 100배 큰 경우가 많아 0.01로 줄임 (파이프라인 규칙인듯)
                obj.scale = (0.01, 0.01, 0.01)
            apply_matching_materials(obj)

    # -------------------------------------------------------------------
    # ▼ [모드 2] Link 방식
    # -------------------------------------------------------------------
    def execute_link_mode(self, context, selected_items):
        base_path = get_project_paths()
        if not base_path:
             self.report({'ERROR'}, "Base Path Error")
             return

        for category, item in selected_items:
            self.process_selected_item_link(item, category, f"{category.name}_col", base_path, context)

    def process_selected_item_link(self, item, category, category_col_name, base_path, context):
        import os
        asset_name = item.name
        blend_file_path = self.get_blend_file_path(base_path, category.name, asset_name)

        if not blend_file_path or not os.path.exists(blend_file_path):
            self.report({'WARNING'}, f"링크할 원본 .blend 파일을 찾을 수 없습니다: {asset_name}\nPath: {blend_file_path}")
            return
            
        self.link_asset_collection(blend_file_path, category_col_name, asset_name, context)

    def link_asset_collection(self, blend_file_path, category_col_name, asset_name, context):
        asset_col_name = f"{asset_name}_col"
        try:
            with bpy.data.libraries.load(blend_file_path, link=True) as (data_from, data_to):
                if asset_col_name in data_from.collections:
                    data_to.collections = [asset_col_name]
                else:
                    self.report({'WARNING'}, f"파일 안에 '{asset_col_name}' 컬렉션이 없습니다: {os.path.basename(blend_file_path)}")
                    return None
        except Exception as e:
            self.report({'ERROR'}, f"파일 링크 실패: {e}")
            return None

        # 링크된 컬렉션을 씬에 인스턴스로 배치
        linked_collection = data_to.collections[0] # 위에서 로드한 컬렉션
        if not linked_collection: return

        # 상위 카테고리 컬렉션 확보
        if category_col_name not in bpy.data.collections:
            cat_col = bpy.data.collections.new(category_col_name)
            context.scene.collection.children.link(cat_col)
        else:
            cat_col = bpy.data.collections[category_col_name]

        # Collection Instance(Empty) 생성
        instance_empty = bpy.data.objects.new(asset_name, None)
        instance_empty.instance_type = 'COLLECTION'
        instance_empty.instance_collection = linked_collection
        instance_empty.scale = (0.01, 0.01, 0.01) # 스케일 보정

        cat_col.objects.link(instance_empty)

        # Library Override 적용
        try:
            bpy.ops.object.select_all(action='DESELECT')
            context.view_layer.objects.active = instance_empty
            instance_empty.select_set(True)
            bpy.ops.object.library_override_hierarchy_create(object=instance_empty, collection=instance_empty.instance_collection)
            print(f"[SF Import] Linked & Overridden: {asset_name}")
        except Exception as e:
            self.report({'ERROR'}, f"라이브러리 오버라이드 생성 실패: {e}")

    # -------------------------------------------------------------------
    # ▼ 공용 헬퍼
    # -------------------------------------------------------------------
    def get_blend_file_path(self, base_path, category_name, asset_name):
        import os
        # 일반 경로
        # category_name이 'ch'나 'bg' 등을 포함하는지 확인
        folder = "prop" # default
        if "ch" in category_name: folder = "ch"
        elif "bg" in category_name: folder = "bg"
        elif "prop" in category_name: folder = "prop"
        
        return os.path.join(base_path, "assets", folder, asset_name, "mod", f"{asset_name}.blend")

    # (이하 apply_light_mask 등 메서드는 기존 코드의 로직이 길어서 생략했습니다. 
    #  클래스 내부에 `apply_light_mask_to_collection` 과 `apply_subdivision_to_meshes` 메서드가 
    #  기존 코드에 정의되어 있다면 그대로 두시거나, 아래에 복사해서 넣으시면 됩니다.)
    
    def apply_light_mask_to_collection(self, asset_col_name, context):
        # ... 기존 코드 복사 ...
        asset_col = bpy.data.collections.get(asset_col_name)
        if not asset_col: return
        mesh_objects = [obj for obj in asset_col.all_objects if obj.type == 'MESH']
        for obj in mesh_objects:
            if not hasattr(obj, "light_mask_applied") or not obj.get("light_mask_applied"):
                # 뷰레이어 체크 생략하고 강제 진행하거나 try-except
                try:
                    obj.select_set(True)
                    bpy.ops.object.apply_light_mask()
                    obj["light_mask_applied"] = True
                    obj.select_set(False)
                except:
                    pass
        if "ViewLayer" in bpy.context.scene.view_layers:
            context.window.view_layer = bpy.context.scene.view_layers["ViewLayer"]

    def apply_subdivision_to_meshes(self, asset_col_name):
        # ... 기존 코드 복사 ...
        asset_col = bpy.data.collections.get(asset_col_name)
        if not asset_col: return
        mesh_objects = [obj for obj in asset_col.all_objects if obj.type == 'MESH']
        for obj in mesh_objects:
            if "_ns_geo" not in obj.name:
                if "Subdivision" not in [mod.name for mod in obj.modifiers]:
                    subdivision_modifier = obj.modifiers.new(name="Subdivision", type='SUBSURF')
                    subdivision_modifier.levels = 1
                    subdivision_modifier.render_levels = 2

class SF_OT_ResetMaterialOperator(bpy.types.Operator):
    bl_idname = "sf.reset_material_operator"
    bl_label = "Reset Material"

    def execute(self, context):
        scene = context.scene
        bpy.context.window.view_layer = bpy.context.scene.view_layers["ViewLayer"]

        selected_assets = [item.name for category in scene.sf_file_categories for item in category.items if item.is_selected]
        for asset_name in selected_assets:
            light_obj_name = f"{asset_name}_light"
            light_obj = bpy.data.objects.get(light_obj_name)

            if not light_obj:
                self.report({'ERROR'}, f"Object {light_obj_name} not found.")
                continue

            category_name = next(cat.name for cat in scene.sf_file_categories if any(item.name == asset_name for item in cat.items))
            blend_file_path = self.get_blend_file_path(category_name, asset_name)

            self.reset_materials_and_keep_drivers(blend_file_path, asset_name, light_obj)

        return {'FINISHED'}

    def get_blend_file_path(self, category_name, asset_name):
        if "ch" in category_name:
            return os.path.join(get_character_dir(), asset_name, "mod", f"{asset_name}.blend")
        elif "bg" in category_name:
            return os.path.join(get_background_dir(), asset_name, "mod", f"{asset_name}.blend")
        elif "prop" in category_name:
            return os.path.join(get_prop_dir(), asset_name, "mod", f"{asset_name}.blend")
        return None

    def reset_materials_and_keep_drivers(self, blend_file_path, asset_name, light_obj):
        try:
            with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
                data_to.materials = data_from.materials
                print(f"Materials from {blend_file_path} loaded successfully.")

            for mat in data_to.materials:
                if '.' in mat.name:
                    mat.name = mat.name.split('.')[0]

            asset_col_name = f"{asset_name}_col"
            asset_col = bpy.data.collections.get(asset_col_name)
            if not asset_col:
                print(f"Collection '{asset_col_name}' not found.")
                return

            for obj in asset_col.objects:
                if obj.type == 'MESH' and obj.data.materials:
                    for i, mat_slot in enumerate(obj.data.materials):
                        if mat_slot:
                            original_mat_name = mat_slot.name.split('.')[0]
                            new_mat = next((mat for mat in data_to.materials if mat.name == original_mat_name), None)
                            if new_mat:
                                obj.data.materials[i] = new_mat

            self.relink_drivers(light_obj, asset_col_name)

        except OSError as e:
            print(f"Error loading file {blend_file_path}: {e}")

    def relink_drivers(self, light_obj, asset_col_name):
        collection = bpy.data.collections.get(asset_col_name)
        if not collection:
            print(f"Collection '{asset_col_name}' not found")
            return

        properties_info = self.get_properties_info()
        if not properties_info:
            print("Failed to load properties info.")
            return

        for obj in collection.objects:
            if obj.type == 'MESH' and obj.data.materials:
                for mat in obj.data.materials:
                    if mat.use_nodes:
                        for node in mat.node_tree.nodes:
                            if node.type == 'GROUP' and node.node_tree and node.node_tree.name == "SF_Toon_Logic":
                                for prop_info in properties_info:
                                    prop_name = prop_info['name']
                                    default = prop_info['default']
                                    prop_type = prop_info['type']
                                    input_idx = prop_info['index']
                                    self.add_driver_to_material(mat, node, prop_name, default, prop_type, input_idx, light_obj)

    def get_properties_info(self):
        file_path = 'T:/_json/get_properties_info.json'
        try:
            with open(file_path, 'r') as infile:
                return json.load(infile)
        except Exception as e:
            print(f"Error loading properties info from {file_path}: {e}")
            return []

    def add_driver_to_material(self, mat, node, prop_name, default, prop_type, input_idx, light_obj):
        node_input = node.inputs[input_idx] if input_idx < len(node.inputs) else None
        if node_input:
            path = f'nodes["{node.name}"].inputs[{input_idx}].default_value'
            if prop_type == "COLOR":
                for idx in range(4):
                    fcurve = mat.node_tree.driver_add(path, idx)
                    self.setup_driver(fcurve, light_obj, prop_name, idx)
            elif prop_type == "FLOAT":
                fcurve = mat.node_tree.driver_add(path)
                self.setup_driver([fcurve], light_obj, prop_name)

    def setup_driver(self, fcurves, obj, prop_name, idx=None):
        if not isinstance(fcurves, list):
            fcurves = [fcurves]
        for fcurve in fcurves:
            driver = fcurve.driver
            driver.type = 'AVERAGE'
            var = driver.variables.new()
            var.targets[0].id = obj
            if idx is not None:
                var.targets[0].data_path = f'["{prop_name}"][{idx}]'
            else:
                var.targets[0].data_path = f'["{prop_name}"]'


class SF_OT_UpdateSelectedOperator(bpy.types.Operator):
    bl_idname = "sf.update_selected_operator"
    bl_label = "Update Selected"

    def execute(self, context):
        scene = context.scene
        my_tool = scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        base_path = get_project_paths()  # 파일 경로의 기본 부분
        
        # "ch" 카테고리에 있는 캐릭터의 MeshSequenceCache 경로 업데이트
        self.update_ch_category(scene, base_path, scene_number, cut_number)
        
        # 나머지 카테고리 처리
        self.update_other_categories(scene, base_path, scene_number, cut_number)

        return {'FINISHED'}
        
    def refresh_linked_libraries(self):
        # 모든 링크된 라이브러리를 반복
        for library in bpy.data.libraries:
            # 리프래시 메서드 호출
            library.reload()

    def update_ch_category(self, scene, base_path, scene_number, cut_number):
        for cache in bpy.data.cache_files.values():
            if "_ch_" in cache.name:
                parts = cache.name.split('_')
                if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                    parts[1] = scene_number
                    parts[2] = cut_number
                    new_name = '_'.join(parts)
                    new_filepath = os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache", new_name)
                    cache.filepath = new_filepath
                    print(f"Updated cache file path for {cache.name} to {new_filepath}")
                    cache.name = new_name
                    print(f"Updated cache name to {new_name}")

    def update_other_categories(self, scene, base_path, scene_number, cut_number):
        for category in scene.sf_file_categories:
            if category.name != "ch":
                for item in category.items:
                    if item.is_selected:  # 아이템이 선택되었을 때만 처리
                        asset_col_name = f"{item.name}_col"
                        if bpy.data.collections.get(asset_col_name):
                            # 선택된 아이템에 대한 컬렉션의 오브젝트를 지우고
                            self.clear_collection(asset_col_name)
                            self.refresh_linked_libraries()
                            bpy.ops.sf.cleanup_orphans_combined1()
                            # 선택된 어셋을 다시 가져온다
                            bpy.ops.sf.import_selected_operator('INVOKE_DEFAULT')
        self.apply_matching_materials()
    
    def clear_collection(self, collection_name):
        collection = bpy.data.collections.get(collection_name)
        if collection:
            for obj in collection.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            print(f"Cleared all objects in collection: {collection_name}")

    def apply_matching_materials(self):
        materials = bpy.data.materials

        for obj in bpy.context.selected_objects:
            obj_data = obj.data
            if obj_data and hasattr(obj_data, "materials"):
                for i, slot in enumerate(obj.material_slots):
                    material_name = slot.name

                    # material_name에서 'MIA_'를 'MI_'로 대체합니다.
                    material_name = material_name.replace('MIA_', 'MI_')

                    # ':'를 기준으로 문자열을 분할하고 마지막 부분을 가져옵니다.
                    if ':' in material_name:
                        material_name = material_name.split(":")[-1]

                    # '.'를 기준으로 문자열을 분할하고 첫 번째 부분을 베이스 메터리얼 이름으로 사용합니다.
                    base_material_name = material_name.split(".")[0]

                    if base_material_name in materials:
                        mat = materials.get(base_material_name)
                        if mat is None:
                            mat = materials.new(name=base_material_name)
                        if obj_data.materials:
                            obj_data.materials[i] = mat
                        else:
                            obj_data.materials.append(mat)

class SF_OT_UpdateSelectedLightOperator(bpy.types.Operator):
    bl_idname = "sf.update_selected_light_operator"
    bl_label = "Update Selected Light"

    def execute(self, context):
        print("Starting operator execution...")
        scene = context.scene
        my_tool = scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        base_path = get_project_paths()  # 파일 경로의 기본 부분
        print(f"Base path acquired: {base_path}")
        print(f"Scene number: {scene_number}, Cut number: {cut_number}")

        # 나머지 카테고리 처리
        self.update_other_categories(scene, base_path, scene_number, cut_number)

        print("Finished operator execution.")
        return {'FINISHED'}
        
    def refresh_linked_libraries(self):
        print("Refreshing linked libraries...")
        for library in bpy.data.libraries:
            library.reload()
        print("All linked libraries refreshed.")

    def update_other_categories(self, scene, base_path, scene_number, cut_number):
        print("Updating other categories...")
        for category in scene.sf_file_categories:
            # print(f"Processing category: {category.name}")
            if category.name != "prop":
                for item in category.items:
                    asset_col_light_name = f"{item.name}_light_col"
                    if bpy.data.collections.get(asset_col_light_name):
                        print(f"Clearing collection: {asset_col_light_name}")
                        # self.clear_collection(asset_col_light_name)
                        self.delete_collection(asset_col_light_name)
                        self.refresh_linked_libraries()
                        bpy.ops.sf.cleanup_orphans_combined1()
                        print(f"Orphans cleaned up for: {asset_col_light_name}")
                        if item.is_selected:
                            print(f"Linking assets for: {item.name}")
                            bpy.ops.sf.link_class()
                    else:
                        print(f"No collection found for: {asset_col_light_name}")
    
    def delete_collection(self, collection_name):
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            print(f"Collection '{collection_name}' not found.")
            return

        # Find all parent collections and unlink this collection
        all_collections = bpy.data.collections  # Get all collections in the data
        for parent in all_collections:  # Iterate over all collections
            if collection.name in parent.children:  # Check if the target collection is a child
                parent.children.unlink(collection)  # Unlink the target collection from the parent

        # Now that the collection is unlinked from all parents, check if it can be deleted
        if collection.users == 0:
            bpy.data.collections.remove(collection)
            print(f"Collection '{collection_name}' has been removed.")
        else:
            print(f"Collection '{collection_name}' still has users and was not removed.")



           
class SF_OT_ApplyLineArt(bpy.types.Operator):
    bl_idname = "sf.apply_line_art"
    bl_label = "Line Art"

    def execute(self, context):
        scene = context.scene
        my_tool = context.scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        base_path = get_project_paths()

        for category in scene.sf_file_categories:
            category_col_name = f"{category.name}_col"

            for item in category.items:
                if item.is_selected:
                    asset_name = item.name
                    asset_col_name = f"{asset_name}_col"
                    directory = os.path.join(base_path, scene_number, cut_number, "ren", "cache")
                    asset_file_path = find_asset_file_path(directory, asset_name)

                    # 지오메트리 노드 설정이 적용될 객체를 찾습니다.
                    asset_line_obj_name = f"{asset_name}_line"
                    asset_line_obj = bpy.data.objects.get(asset_line_obj_name)
                    
                    # 지오메트리 노드 설정을 적용합니다.
                    if asset_line_obj and asset_line_obj.type == 'MESH' and "GeometryNodes" in asset_line_obj.modifiers:
                        self.apply_geometry_nodes_settings(asset_line_obj, asset_col_name)

        return {'FINISHED'}
        

    def apply_geometry_nodes_settings(self, asset_line_obj, asset_col_name):
        # asset_line_obj가 메시 객체인지 확인
        if asset_line_obj and asset_line_obj.type == 'MESH':
            # Scene (input_1)에 어셋 이름에 기반한 컬렉션 지정
            if asset_col_name in bpy.data.collections:
                asset_line_obj.modifiers["GeometryNodes"]["Input_1"] = bpy.data.collections[asset_col_name]
            # Camera (input_5)에 현재 활성화된 카메라 지정
            if bpy.context.scene.camera:
                asset_line_obj.modifiers["GeometryNodes"]["Input_5"] = bpy.context.scene.camera  
            asset_line_obj.modifiers["GeometryNodes"]["Input_15"] = bpy.context.scene.input_15
            asset_line_obj.modifiers["GeometryNodes"]["Input_16"] = bpy.context.scene.input_16
            asset_line_obj.modifiers["GeometryNodes"]["Socket_0"] = True
            asset_line_obj.modifiers["GeometryNodes"]["Input_11"] = False
            asset_line_obj.modifiers["GeometryNodes"]["Input_20"] = False
            asset_line_obj.modifiers["GeometryNodes"]["Input_31"] = True
            asset_line_obj.modifiers["GeometryNodes"]["Input_10"] = True        
            # 레졸루션 X와 Y를 가져와 각각 지오메트리 노드에 적용
            asset_line_obj.modifiers["GeometryNodes"]["Input_4"] = bpy.context.scene.render.resolution_x
            asset_line_obj.modifiers["GeometryNodes"]["Input_3"] = bpy.context.scene.render.resolution_y
            
            # 씬 카메라의 FOV값을 가져와서 +10 한 다음 그 값을 radian으로 변환해 지오메트리 노드에 적용
        if bpy.context.scene.camera and bpy.context.scene.camera.data.type == 'PERSP':
            fov_in_radians = bpy.context.scene.camera.data.angle
            fov_in_degrees = fov_in_radians * (180 / math.pi)  # 라디안을 도로 변환
            fov_in_degrees += 10  # 10도를 더함
            asset_line_obj.modifiers["GeometryNodes"]["Input_48"] = fov_in_degrees  # 변환된 값을 적용

        
    def append_materials_and_collection_from_blend1(self, blend_file_path, asset_name, category_name):
        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
            data_to.materials = data_from.materials

        for mat in data_to.materials:
            if '.' in mat.name:
                mat.name = mat.name.split('.')[0]



    def import_asset(self, asset_file_path, category_col_name, asset_col_name, category_name, context):
        scene = context.scene

        # 카테고리 컬렉션 확인 및 생성
        category_col = bpy.data.collections.get(category_col_name)
        if not category_col:
            category_col = bpy.data.collections.new(category_col_name)
            scene.collection.children.link(category_col)

        # 어셋 컬렉션 확인 및 생성
        asset_col = category_col.children.get(asset_col_name)
        if not asset_col:
            asset_col = bpy.data.collections.new(asset_col_name)
            category_col.children.link(asset_col)

        # 컬렉션이 비활성화 되어있다면 활성화
        layer_collection = bpy.context.view_layer.layer_collection
        layer_collection = self.find_layer_collection(layer_collection, asset_col_name)
        if layer_collection and not layer_collection.collection.hide_viewport:
            layer_collection.collection.hide_viewport = False

        # 해당 컬렉션에 오브젝트가 없는 경우에만 임포트 진행
        if not asset_col.objects:
            # 파일 존재 여부 확인
            if not os.path.exists(asset_file_path):
                self.report({'ERROR'}, f"Asset file not found: {asset_file_path}")
                return {'CANCELLED'}

            # 파일 경로를 사용하여 어셋 임포트
            bpy.ops.wm.usd_import(filepath=asset_file_path, relative_path=True, import_subdiv=False, set_frame_range=False)

            # 임포트된 어셋 중 루트 객체의 스케일 조정 및 머티리얼 적용
            for obj in asset_col.objects:
                if obj.parent is None:
                    obj.scale = (0.01, 0.01, 0.01)
                    self.apply_matching_materials(obj)
                    bpy.ops.sf.cleanup_orphans_combined1()

    def find_layer_collection(self, layer_collection, collection_name):
        """ Recursively find a layer collection by name """
        if layer_collection.name == collection_name:
            return layer_collection
        for child in layer_collection.children:
            result = self.find_layer_collection(child, collection_name)
            if result:
                return result
        return None

class SF_OT_updateMaterialOperator(bpy.types.Operator):
    bl_idname = "sf.update_materials"
    bl_label = "Update Materials from Blend File"
    bl_options = {'REGISTER', 'UNDO'}

    def apply_matching_materials(self, obj, materials_dict):
        for slot in obj.material_slots:
            mat = slot.material
            if mat:
                processed_name = mat.name
                if ':' in processed_name:
                    processed_name = processed_name.split(':')[-1]
                if '.' in processed_name:
                    processed_name = '.'.join(processed_name.split('.')[:-1])
                if processed_name in materials_dict:
                    slot.material = materials_dict[processed_name]

    def get_blend_file_path(self, asset_name, category_name, scene_number, cut_number):
        base_path = get_project_paths()
        return os.path.join(base_path, "assets", category_name, asset_name, "mod", f"{asset_name}.blend")

    def execute(self, context):
        scene = context.scene
        my_tool = context.scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number

        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    asset_name = item.name
                    blend_file_path = self.get_blend_file_path(asset_name, category.name, scene_number, cut_number)
                    asset_col_name = f"{asset_name}_col"

                    # 어셋 컬렉션 확인
                    asset_col = bpy.data.collections.get(asset_col_name)
                    if not asset_col:
                        self.report({'ERROR'}, f"Collection '{asset_col_name}' not found.")
                        continue
                    
                    # 어셋 컬렉션 하위 모든 메쉬 객체의 메터리얼 별명 생성
                    material_alias_dict = {}
                    def get_mesh_objects_recursive(collection):
                        for obj in collection.objects:
                            if obj.type == 'MESH':
                                for slot in obj.material_slots:
                                    mat = slot.material
                                    if mat:
                                        processed_name = mat.name
                                        if ':' in processed_name:
                                            processed_name = processed_name.split(':')[-1]
                                        if '.' in processed_name:
                                            processed_name = '.'.join(processed_name.split('.')[:-1])
                                        material_alias_dict[processed_name] = mat
                            for child_col in collection.children:
                                get_mesh_objects_recursive(child_col)

                    get_mesh_objects_recursive(asset_col)

                    # 블렌드 파일에서 메터리얼 로드
                    materials_dict = {}
                    try:
                        with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
                            data_to.materials = data_from.materials
                        for mat in data_to.materials:
                            if mat:
                                processed_name = mat.name
                                if ':' in processed_name:
                                    processed_name = processed_name.split(':')[-1]
                                if '.' in processed_name:
                                    processed_name = '.'.join(processed_name.split('.')[:-1])
                                materials_dict[processed_name] = mat
                        print(f"Materials from {blend_file_path} loaded successfully.")
                    except Exception as e:
                        self.report({'ERROR'}, f"Failed to load materials from blend file: {str(e)}")
                        continue

                    # 어셋 컬렉션 하위 메쉬 객체에 메터리얼 적용
                    def apply_materials_recursive(collection):
                        for obj in collection.objects:
                            if obj.type == 'MESH':
                                self.apply_matching_materials(obj, materials_dict)
                        for child_col in collection.children:
                            apply_materials_recursive(child_col)
                    apply_materials_recursive(asset_col)
                    bpy.ops.object.sf_add_properties_and_link1()
        return {'FINISHED'}

class SF_OT_UpdateMaterialsOperator(bpy.types.Operator):
    bl_idname = "sf.update_materials_operator"
    bl_label = "Update Materials"

    def execute(self, context):
        base_path = get_project_paths()

        for category in context.scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:  # UI에서 사용자가 선택한 항목만 처리
                    asset_name = item.name
                    category_name = self.get_category_name(asset_name)
                    blend_file_path = os.path.join(base_path, "assets", category_name, asset_name, "mod", f"{asset_name}.blend")

                    if os.path.exists(blend_file_path):
                        self.update_materials_from_blend(context, blend_file_path, asset_name)
                    else:
                        self.report({'WARNING'}, f"Blend file not found for {asset_name}")

        print("Material update complete.")
        return {'FINISHED'}

    def update_materials_from_blend(self, context, blend_file_path, asset_name):
        """
        어셋의 Blend 파일에서 메터리얼을 어팬드하고, 해당 메터리얼로 교체합니다.
        """
        # Load original materials
        original_materials = self.append_materials_from_blend(blend_file_path)

        if not original_materials:
            self.report({'ERROR'}, f"No materials found in {blend_file_path}")
            return

        # Process materials in the scene
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                self.replace_object_materials(obj, original_materials)
            else:
                print(f"Skipped {obj.name}: Not a mesh object.")

    def append_materials_from_blend(self, blend_file_path):
        """
        어팬드된 메터리얼 리스트를 반환합니다.
        """
        try:
            existing_materials = set(bpy.data.materials.keys())
            with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
                data_to.materials = data_from.materials

            # Find newly appended materials
            new_materials = [bpy.data.materials[mat_name] for mat_name in bpy.data.materials.keys() if mat_name not in existing_materials]
            print(f"Appended materials: {[mat.name for mat in new_materials]}")
            return new_materials

        except Exception as e:
            print(f"Error appending materials from {blend_file_path}: {e}")
            return []

    def replace_object_materials(self, obj, original_materials):
        """
        오브젝트의 메터리얼을 원본 메터리얼로 교체합니다.
        """
        for slot in obj.material_slots:
            if not slot.material:
                continue

            scene_material_name = slot.material.name.split(".")[0].lower()  # 씬 메터리얼 이름의 앞부분
            matching_material = next(
                (mat for mat in original_materials if mat.name.split(".")[0].lower() == scene_material_name),
                None
            )

            if matching_material:
                print(f"Replacing material '{slot.material.name}' with '{matching_material.name}' on '{obj.name}'")
                slot.material = matching_material
            else:
                print(f"No matching material found for '{slot.material.name}' on '{obj.name}'")

    def get_category_name(self, asset_name):
        """
        어셋 이름을 기반으로 카테고리를 결정합니다.
        """
        character_names = get_character_names()
        bg_names = get_bg_names()
        prop_names = get_prop_names()

        if asset_name in character_names:
            return "ch"
        elif asset_name in bg_names:
            return "bg"
        elif asset_name in prop_names:
            return "prop"
        else:
            return "prop"


        
class SF_OT_ImportSceneCameraOperator(bpy.types.Operator):
    bl_idname = "sf.import_scene_camera"
    bl_label = "Import Scene Camera"

    def execute(self, context):
        scene = context.scene
        my_tool = scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        base_path = get_project_paths()
        project_prefix = get_project_prefix()

        # 카메라 이름
        camera_name = f"{project_prefix}_{scene_number}_{cut_number}_cam"
        print(f"Camera file name: {camera_name}")

        # FBX 경로
        camera_file_path = os.path.join(
            base_path, "scenes", scene_number, cut_number, "ren", "cache", f"{camera_name}.fbx"
        )
        print(f"Camera file path: {camera_file_path}")

        # JSON 경로
        json_file_name = f"{project_prefix}_{scene_number}_{cut_number}_camera_data.json"
        full_json_path = os.path.join(
            base_path, "scenes", scene_number, cut_number, "ren", "cache", json_file_name
        )
        print(f"JSON file path: {full_json_path}")

        # 씬 내 카메라 이름
        camera_name_scene = f"{project_prefix}_cam_{scene_number}_{cut_number}"
        print(f"Scene camera name: {camera_name_scene}")

        # 기존 카메라 삭제
        if camera_name_scene in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[camera_name_scene], do_unlink=True)

        # FBX 가져오기
        if os.path.exists(camera_file_path):
            context.view_layer.active_layer_collection = context.view_layer.layer_collection
            bpy.ops.import_scene.fbx(filepath=camera_file_path, anim_offset=0.0)

            # 카메라 아닌 오브젝트 삭제
            imported_objects = [obj for obj in bpy.context.selected_objects if obj.type != 'CAMERA']
            for obj in imported_objects:
                bpy.data.objects.remove(obj, do_unlink=True)

            # 카메라 속성 세팅
            camera = bpy.data.objects.get(camera_name_scene)
            if camera is not None:
                camera.data.passepartout_alpha = 1
                camera.data.clip_start = 0.05
                camera.data.clip_end = 50
                camera.data.sensor_fit = 'HORIZONTAL'

            # 🔥 JSON 읽기 및 1/2 해상도 완벽 보정 로직 🔥
            if os.path.exists(full_json_path):
                with open(full_json_path, 'r') as json_file:
                    camera_data = json.load(json_file)

                    # 프레임 범위 적용
                    scene.frame_start = int(camera_data.get('minTime', scene.frame_start))
                    scene.frame_end = int(camera_data.get('maxTime', scene.frame_end))

                    json_w = camera_data.get('resolutionX')
                    json_h = camera_data.get('resolutionY')

                    if json_w and json_h:
                        if json_w < 2500:
                            final_w = int(json_w * 2)
                            final_h = int(json_h * 2)
                        else:
                            final_w = int(json_w)
                            final_h = int(json_h)
                    else:
                        if project_prefix == "DSC":
                            final_w, final_h = 4096, 1716
                        elif project_prefix == "ttm":
                            final_w, final_h = 3840, 1634
                        else:
                            final_w, final_h = 1920, 1080

                    # 홀수 보정
                    if final_h % 2 != 0:
                        final_h += 1
                    if final_w % 2 != 0:
                        final_w += 1

                    scene.render.resolution_x = final_w
                    scene.render.resolution_y = final_h
                    
                    # 🔥 [해상도 % 100% 고정]
                    scene.render.resolution_percentage = 100

                return {'FINISHED'}

        else:
            self.report({'WARNING'}, "Camera file not found.")

        return {'FINISHED'}


# ---- publish 경로: 항상 base_name 기준으로 만듦 ----
def get_published_blend_path(project, category, asset_name):
    base_name = get_asset_base_name(asset_name)

    # 기존 프로젝트별 루트 규칙을 유지 (필요 시 너희 파일의 기존 로직으로 교체)
    if project == 'DSC' or project == 'dsc':
        base = "S:/assets"
    elif project == 'BTS':
        base = "B:/assets"        
    elif project == 'THE_TRAP':
        base = "T:/assets"
    elif project == 'ARBOBION':
        base = "A:/assets"
    elif project == 'FUZZ':
        base = "Z:/assets"        
    else:
        base = "S:/assets"  # fallback

    # 파이프라인 규칙: assets/<카테고리>/<어셋>/mod/<어셋>.blend
    return os.path.join(base, category, base_name, "mod", f"{base_name}.blend")


def _get_modifier_cache_object_paths(mod):
    """Return cache_file.object_paths as plain strings, safely."""
    cf = getattr(mod, 'cache_file', None)
    if not cf:
        return []

    try:
        return [p.path for p in cf.object_paths if getattr(p, 'path', None)]
    except Exception:
        return []


def _cache_path_leaf(path):
    return path.rstrip('/').split('/')[-1]


def _rank_cache_object_path(path, asset_name=None):
    """Lower score is better. Prefer real geo object prims over look/material paths."""
    score = 100

    normalized = path.rstrip('/')
    if '/Looks/' in normalized:
        score += 1000
    if '/geo/' in normalized:
        score -= 50
    if asset_name and f'/{asset_name}/geo/' in normalized:
        score -= 25

    depth = normalized.count('/')
    score += depth
    return score


def _find_best_cache_object_path(mod, obj_name, asset_name=None):
    """
    Look up an existing USD prim path from cache_file.object_paths by Blender object name.
    This never fabricates a new path string. It only returns one of the existing cache paths.
    """
    base_name = obj_name.split('.')[0]
    base_name_l = base_name.lower()
    paths = _get_modifier_cache_object_paths(mod)
    if not paths:
        return None

    # 1) Exact leaf-name match
    exact = [p for p in paths if _cache_path_leaf(p) == base_name]
    if exact:
        return sorted(exact, key=lambda p: _rank_cache_object_path(p, asset_name))[0]

    # 2) Case-insensitive exact leaf-name match
    exact_ci = [p for p in paths if _cache_path_leaf(p).lower() == base_name_l]
    if exact_ci:
        return sorted(exact_ci, key=lambda p: _rank_cache_object_path(p, asset_name))[0]

    # 3) Very loose fallback for naming drift, still choosing from existing cache paths only
    loose = []
    for p in paths:
        leaf = _cache_path_leaf(p)
        leaf_l = leaf.lower()
        if leaf_l.endswith(base_name_l) or base_name_l.endswith(leaf_l):
            loose.append(p)

    if loose:
        return sorted(loose, key=lambda p: _rank_cache_object_path(p, asset_name))[0]

    return None


def _sync_modifier_object_path_from_cache(mod, obj_name, asset_name=None):
    """
    Update mod.object_path only when a matching path is found in cache_file.object_paths.
    If no match is found, keep the existing object_path untouched.
    """
    found_path = _find_best_cache_object_path(mod, obj_name, asset_name=asset_name)
    if not found_path:
        return False, getattr(mod, 'object_path', ''), getattr(mod, 'object_path', '')

    old_path = getattr(mod, 'object_path', '')
    if old_path != found_path:
        mod.object_path = found_path
    return True, old_path, found_path


def update_usd_cache(usd_path, objects):
    import os
    usd_path = usd_path.replace("\\", "/")
    usd_file_name = os.path.basename(usd_path)

    print(f"[DEBUG] update_usd_cache for {[obj.name for obj in objects]}")

    for obj in objects:
        if obj.type != 'MESH':
            continue

        print(f"[DEBUG] Updating: {obj.name}")

        mod = next((m for m in obj.modifiers if m.type == 'MESH_SEQUENCE_CACHE'), None)
        if not mod:
            print(f"[SKIP] No MeshSequenceCache on {obj.name}; existing modifier only policy.")
            continue

        try:
            cache = bpy.data.cache_files.load(usd_path)
            mod.cache_file = cache
        except RuntimeError:
            mod.cache_file = bpy.data.cache_files.get(usd_file_name)

        if mod.cache_file:
            mod.cache_file.filepath = usd_path
            mod.cache_file.name = usd_file_name

        matched, old_path, new_path = _sync_modifier_object_path_from_cache(mod, obj.name)
        if matched:
            print(f"[✅] Cache linked to {obj.name} → {usd_path} | object_path={new_path}")
        else:
            print(f"[WARN] {obj.name}: matching object_path not found in cache_file.object_paths, keeping existing path: {old_path}")



class SF_MaterialSwitcherProperties(bpy.types.PropertyGroup):
    use_existing_materials: bpy.props.BoolProperty(
        name="Use Existing Materials",
        default=True
    )

    import_mode: bpy.props.EnumProperty(
        name="Import Mode",
        description="어셋 임포트 방식",
        items=[
            ('AS_NEW', "As New", "기존 어셋을 삭제하고 새로 불러오기"),
            ('USE_EXISTING', "Use Existing", "기존 어셋 유지, 머티리얼만 교체")
        ],
        default='USE_EXISTING'
    )
    
def get_usd_path(scene_number, cut_number, asset_name, project, category_name=None):
    prefix = get_project_prefix(project)
    base_path = get_project_paths(project)

    # category_name이 비어있을 경우 기본값 보정
    if not category_name:
        category_name = "ch"

    usd_filename = f"{prefix}_{scene_number}_{cut_number}_{category_name}_{asset_name}.usd"
    return os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache", usd_filename)

class SF_OT_ImportAndUpdateOperatorDSC(bpy.types.Operator):
    bl_idname = "sf.import_and_update_operator_dsc"
    bl_label = "Import and Update Asset (Final)"
    bl_description = "어셋이 없으면 Import하고, 있으면 USD 캐시를 갱신합니다."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import os
        scene = context.scene
        my_tool = scene.my_tool
        
        # 1. 프로젝트 설정
        try:
            config = get_current_config()
            base_path = config['drive']
            prefix = config['prefix']
        except:
            base_path = "B:/"
            prefix = "BTS"

        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        updated_count = 0

        # 2. 선택된 어셋 처리
        for category in scene.sf_file_categories:
            for item in category.items:
                if not item.is_selected:
                    continue

                asset_name = item.name
                category_name = category.name

                # (A) USD 캐시 경로 계산
                usd_filename = f"{prefix}_{scene_number}_{cut_number}_{category_name}_{asset_name}.usd"
                usd_path = os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache", usd_filename).replace("\\", "/")
                
                # USD 파일 존재 여부 확인
                has_usd = os.path.exists(usd_path)
                
                # 🔥 [수정 완료] 와일드카드 검색 시 정확한 카테고리와 어셋명 매칭 규칙 적용
                search_target = f"_{category_name}_{asset_name}.".lower()
                if not has_usd and os.path.exists(os.path.dirname(usd_path)):
                     for f in os.listdir(os.path.dirname(usd_path)):
                        if f.lower().endswith(".usd") and search_target in f.lower():
                            usd_path = os.path.join(os.path.dirname(usd_path), f).replace("\\", "/")
                            usd_filename = f
                            has_usd = True
                            break

                # (B) 컬렉션 확인
                asset_col_name = f"{asset_name}_col"
                asset_col = bpy.data.collections.get(asset_col_name)

                if not asset_col:
                    print(f"[Import] '{asset_name}' 씬에 없음 -> Import 시작")
                    blend_path = os.path.join(base_path, "assets", category_name, asset_name, "mod", f"{asset_name}.blend")
                    
                    blend_path = blend_path.replace("\\", "/")

                    if not os.path.exists(blend_path):
                        self.report({'ERROR'}, f"Source File Missing: {blend_path}")
                        print(f"[Fail] 소스 파일 없음: {blend_path}")
                        continue
                    
                    try:
                        self.append_and_link_cache_advanced(blend_path, category_name, asset_name, context, usd_path if has_usd else None, usd_filename)
                        updated_count += 1
                        print(f"[Success] '{asset_name}' Import & Sync 완료")
                    except Exception as e:
                        self.report({'ERROR'}, f"Import Failed: {asset_name} - {e}")
                        import traceback
                        traceback.print_exc()

                else:
                    print(f"[Update] '{asset_name}' 씬에 존재함 -> Cache Update")
                    if has_usd:
                        self.update_mesh_sequence_cache_recursive(asset_col, asset_name, usd_path, usd_filename)
                        updated_count += 1
                    else:
                        print(f"[Skip] USD 캐시가 없어서 업데이트 패스: {asset_name}")

        if updated_count > 0:
            self.report({'INFO'}, f"총 {updated_count}개 어셋 처리 완료")
        else:
            self.report({'WARNING'}, "처리된 어셋이 없습니다.")
            
        bpy.ops.sf.update_selected_operator_dsc()
        
        return {'FINISHED'}

    def append_and_link_cache_advanced(self, blend_path, cat_name, asset_name, context, usd_path, usd_file_name):
        target_col_name = f"{asset_name}_col"
        light_col_name = f"{asset_name}_light_col"
        
        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            cols_to_import = []
            if target_col_name in data_from.collections:
                cols_to_import.append(target_col_name)
            if light_col_name in data_from.collections:
                cols_to_import.append(light_col_name)
            data_to.collections = cols_to_import

        if not data_to.collections:
            raise ValueError(f"파일 내에 '{target_col_name}' 컬렉션이 없습니다.")

        parent_col_name = f"{cat_name}_col"
        p_col = bpy.data.collections.get(parent_col_name)
        if not p_col:
            p_col = bpy.data.collections.new(parent_col_name)
            context.scene.collection.children.link(p_col)

        for imported_col in data_to.collections:
            if not imported_col: continue
            
            if imported_col.name not in p_col.children:
                p_col.children.link(imported_col)
            
            if usd_path and "light" not in imported_col.name:
                self.update_mesh_sequence_cache_recursive(imported_col, asset_name, usd_path, usd_file_name)

    def update_mesh_sequence_cache_recursive(self, collection, asset_name, usd_path, usd_file_name):
        for obj in collection.all_objects:
            if obj.type == 'MESH':
                self._apply_cache_to_object(obj, asset_name, usd_path, usd_file_name)

    def _get_existing_cache_file(self, obj):
        for m in obj.modifiers:
            if m.type == 'MESH_SEQUENCE_CACHE' and getattr(m, 'cache_file', None):
                return m.cache_file
        return None

    def _apply_cache_to_object(self, obj, asset_name, usd_path, usd_file_name):
        mod = None
        for m in obj.modifiers:
            if m.type == 'MESH_SEQUENCE_CACHE':
                mod = m
                break
        if not mod:
            print(f"[SKIP] {obj.name}: MeshSequenceCache 모디파이어가 없어 캐시 경로만 갱신하지 못함")
            return

        cf = getattr(mod, 'cache_file', None)
        if not cf:
            print(f"[SKIP] {obj.name}: 기존 cache_file 데이터블록이 없어 캐시 경로만 갱신하지 못함")
            return

        cf.name = usd_file_name
        cf.filepath = usd_path

        try:
            matched, old_path, new_path = _sync_modifier_object_path_from_cache(mod, obj.name, asset_name=asset_name)
            if not matched:
                print(f"[WARN] Prim Path 매칭 실패: {obj.name} | 기존 경로 유지: {old_path}")
        except Exception as e:
            print(f"[WARN] Prim Path 설정 실패: {obj.name} ({e})")
            
            
class SF_OT_ImportSelectedOperatorDSC(bpy.types.Operator):
    bl_idname = "sf.import_selected_operator_dsc"
    bl_label = "Import Selected (DSC Ver)"
    bl_description = "DSC용 퍼블리시 컬렉션 및 USD 캐시 자동 임포트"

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        # layout.prop(self, "import_mode", expand=True)

    def execute(self, context):
        scene = context.scene
        my_tool = scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        project = "DSC"
        prefix = "DSC"

        for category in scene.sf_file_categories:
            for item in category.items:
                if not item.is_selected:
                    continue

                asset_name = item.name
                category_name = category.name
                main_col_name = f"{asset_name}_col"
                light_col_name = f"{asset_name}_light_col"
                collections_to_import = [main_col_name]
                if category_name == "ch":
                    collections_to_import.append(light_col_name)

                blend_path = get_published_blend_path(project, category_name, asset_name)
                usd_path = get_usd_path(scene_number, cut_number, asset_name, project)

                if os.path.exists(blend_path):
                    self.append_collections(blend_path, collections_to_import, category_name)
                    selected_objects = bpy.context.selected_objects[:]
                else:
                    self.report({'WARNING'}, f"⚠️ 퍼블리시/캐시 없음: {asset_name}")
                    continue

                self.ensure_collection_hierarchy(category_name, asset_name)
    
                for obj in selected_objects:
                    apply_matching_materials(obj)

        return {'FINISHED'}

    def delete_collections(self, collection_names):
        for col_name in collection_names:
            if col_name in bpy.data.collections:
                bpy.data.collections.remove(bpy.data.collections[col_name], do_unlink=True)

    def append_collections(self, blend_path, collection_names, category_name):
        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            data_to.collections = [name for name in data_from.collections if name in collection_names]

        for col in data_to.collections:
            if col is None:
                continue

            target_col = bpy.data.collections.get(col.name)
            if not target_col:
                continue

            parent_col_name = f"{category_name}_col"
            parent_col = bpy.data.collections.get(parent_col_name)
            if not parent_col:
                parent_col = bpy.data.collections.new(parent_col_name)
                bpy.context.scene.collection.children.link(parent_col)

            if target_col.name not in parent_col.children:
                parent_col.children.link(target_col)

            if target_col.name in bpy.context.scene.collection.children:
                bpy.context.scene.collection.children.unlink(target_col)

    def import_usd(self, usd_path, asset_name):
        usd_args = {
            "filepath": usd_path,
            "import_materials": True,
            "import_usd_preview": False,
            "import_all_materials": False,
            "import_meshes": True,
            "read_mesh_uvs": True,
            "read_mesh_colors": True,
            "scale": 0.01,
        }

        if bpy.app.version >= (4, 4, 0):
            usd_args["apply_unit_conversion_scale"] = False

        bpy.ops.wm.usd_import(**usd_args)

        bpy.context.view_layer.update()

        # 🔥 [수정 완료] 누락 방어
        imported_objs = [
            obj for obj in bpy.context.selected_objects
            if obj.name.split('.')[0].lower() == asset_name.lower()
        ]

        # Note: 원본 코드의 use_existing 변수 처리 관련 로직 방어를 위해 원본 구조 유지
        try:
            if not use_existing:
                col = bpy.data.collections.get(f"{asset_name}_col") or bpy.data.collections.new(f"{asset_name}_col")
                for obj in imported_objs:
                    for c in obj.users_collection:
                        c.objects.unlink(obj)
                    col.objects.link(obj)
        except NameError:
            pass

        return imported_objs

    def ensure_collection_hierarchy(self, category_name, asset_name):
        category_col_name = f"{category_name}_col"
        asset_col_name = f"{asset_name}_col"

        if category_col_name not in bpy.data.collections:
            category_col = bpy.data.collections.new(category_col_name)
            bpy.context.scene.collection.children.link(category_col)
        else:
            category_col = bpy.data.collections[category_col_name]

        if asset_col_name not in bpy.data.collections:
            asset_col = bpy.data.collections.new(asset_col_name)
        else:
            asset_col = bpy.data.collections[asset_col_name]

        if asset_col.name not in category_col.children:
            category_col.children.link(asset_col)

        if asset_col.name in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.unlink(asset_col)

# class SF_OT_UpdateSelectedOperatorDSC(bpy.types.Operator):
    # bl_idname = "sf.update_selected_operator_dsc"
    # bl_label = "Update Selected (DSC Ver)"
    # bl_description = (
        # "선택한 어셋의 USD 캐시 경로와 Parent Prim Path를 "
        # "씬/컷 기준으로 갱신합니다 (DSC 전용, 인스턴스 대응)"
    # )

    # def execute(self, context):
        # import os
        # scene = context.scene
        # my_tool = scene.my_tool
        # scene_number = my_tool.scene_number
        # cut_number = my_tool.cut_number
        # prefix = "DSC"
        # updated_count = 0

        # for category in scene.sf_file_categories:
            # for item in category.items:
                # if not item.is_selected:
                    # continue  # ✅ 선택된 애셋만 갱신

                # asset_name    = item.name                        # ex: partition
                # base_name     = get_asset_base_name(asset_name)  # ex: partition
                # category_name = category.name

                # usd_filename = f"{prefix}_{scene_number}_{cut_number}_{category_name}_{asset_name}.usd"
                # usd_path = os.path.join("S:/scenes", scene_number, cut_number, "ren", "cache", usd_filename)
                # usd_path = usd_path.replace("\\", "/")  # ✅ 경로 정리

                # found = False

                # # ----------------------------------------------------------
                # # Step 1: CacheFile 갱신 (asset_name 기준만!)
                # # ----------------------------------------------------------
                # for cache in bpy.data.cache_files:
                    # if cache.name == usd_filename:
                        # print(f"[UPDATE] 🔁 CacheFile: '{cache.name}' → {usd_path}")
                        # cache.filepath = usd_path
                        # cache.name = usd_filename
                        # updated_count += 1
                        # found = True
                        # break

                # # ----------------------------------------------------------
                # # Step 2: MeshSequenceCache 모디파이어 갱신 + Prim Path 교체
                # # ----------------------------------------------------------
                # for obj in bpy.data.objects:
                    # for mod in obj.modifiers:
                        # if mod.type == 'MESH_SEQUENCE_CACHE' and mod.cache_file:

                            # # ✅ CacheFile 독립 복제
                            # unique_name = f"{usd_filename}_{obj.name}"
                            # if unique_name not in bpy.data.cache_files:
                                # cf = mod.cache_file.copy()
                                # cf.name = unique_name
                                # cf.filepath = usd_path
                                # print(f"[NEW] CacheFile 복제 생성: {cf.name}")
                            # else:
                                # cf = bpy.data.cache_files[unique_name]
                                # cf.filepath = usd_path
                                # print(f"[REUSE] CacheFile 재사용: {cf.name}")

                            # mod.cache_file = cf

                            # # ✅ Prim Path 갱신
                            # try:
                                # old_path = mod.object_path
                                # parts = old_path.split('/')
                                # if len(parts) > 1:
                                    # parts[1] = asset_name
                                    # new_path = '/'.join(parts)
                                # else:
                                    # new_path = f"/{asset_name}"

                                # mod.object_path = new_path
                                # print(f"[UPDATE] 🪢 Prim Path: {obj.name} | {old_path} → {new_path}")
                            # except Exception as e:
                                # print(f"[WARN] Prim Path 갱신 실패: {obj.name} ({e})")

                            # updated_count += 1
                            # found = True



                # # ----------------------------------------------------------
                # # Step 3: base_name fallback (asset_name이 씬에 없을 때만)
                # # ----------------------------------------------------------
                # if not found:
                    # for cache in bpy.data.cache_files:
                        # if base_name in cache.name:
                            # print(f"[FALLBACK] 🔁 CacheFile base 매칭: '{cache.name}' → {usd_path}")
                            # cache.filepath = usd_path
                            # cache.name = usd_filename
                            # updated_count += 1
                            # found = True
                            # break

                # if not found:
                    # self.report({'WARNING'}, f"⚠️ 캐시 갱신 실패: {asset_name} → {usd_filename}")

        # # ----------------------------------------------------------
        # # 결과 메시지
        # # ----------------------------------------------------------
        # if updated_count == 0:
            # self.report({'WARNING'}, "선택된 어셋에 대해 갱신된 캐시가 없습니다.")
        # else:
            # self.report({'INFO'}, f"✅ 총 {updated_count}개의 캐시 경로/Prim Path를 갱신했습니다.")

        # return {'FINISHED'}

class SF_OT_UpdateSelectedOperatorDSC(bpy.types.Operator):
    bl_idname = "sf.update_selected_operator_dsc"
    bl_label = "Update Selected (Final Fix)"
    bl_description = "선택된 어셋(BG 포함)의 원본을 대조하여 정확한 메쉬에만 USD 캐시를 연결합니다."
    bl_options = {'REGISTER', 'UNDO'}

    def get_blend_file_path(self, base_path, asset_name, category_name):
        """원본 자산의 위치를 찾아오는 로직"""
        import os
        return os.path.join(base_path, "assets", category_name, asset_name, "mod", f"{asset_name}.blend").replace("\\", "/")


    def execute(self, context):
        import os
        scene = context.scene
        my_tool = scene.my_tool
        
        # 1. 프로젝트 설정
        try:
            config = get_current_config()
            base_path = config['drive']
            prefix = config['prefix']
        except:
            base_path = "B:/"
            prefix = "BTS"

        sn, cn = my_tool.scene_number, my_tool.cut_number
        cache_dir = os.path.join(base_path, "scenes", sn, cn, "ren", "cache").replace("\\", "/")
        updated_count = 0

        # UI 선택 어셋 수집
        selected_assets = []
        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    selected_assets.append((category.name, item.name))

        if not selected_assets:
            self.report({'WARNING'}, "선택된 어셋이 없습니다.")
            return {'CANCELLED'}

        # 2. 각 어셋 처리
        for cat_name, asset_name in selected_assets:
            
            # (A) 원본 데이터 파일에서 메쉬 이름 추출
            blend_file_path = self.get_blend_file_path(base_path, asset_name, cat_name)
            valid_mesh_names = []
            
            if os.path.exists(blend_file_path):
                try:
                    with bpy.data.libraries.load(blend_file_path, link=False) as (data_from, data_to):
                        # 🔥 [수정 완료] .split('.') 추가!
                        valid_mesh_names = [name.split('.')[0] for name in data_from.objects]
                except Exception as e:
                    print(f"[WARN] 원본 파일을 읽지 못함: {e}")
            else:
                print(f"[WARN] 원본 파일을 찾을 수 없음: {blend_file_path}")

            # (B) 캐시 USD 경로 찾기
            exact_name = f"{prefix}_{sn}_{cn}_{cat_name}_{asset_name}.usd"
            usd_path = os.path.join(cache_dir, exact_name).replace("\\", "/")
            
            search_target = f"_{cat_name}_{asset_name}.".lower()
            if not os.path.exists(usd_path) and os.path.exists(cache_dir):
                for f in os.listdir(cache_dir):
                    if f.lower().endswith(".usd") and search_target in f.lower():
                        usd_path = os.path.join(cache_dir, f).replace("\\", "/")
                        exact_name = f
                        break
            
            if not os.path.exists(usd_path):
                print(f"[Fail] USD 캐시 없음: {asset_name}")
                continue

            # (C) 오브젝트 깐깐하게 필터링
            target_objs = []
            asset_col = bpy.data.collections.get(f"{asset_name}_col")
            
            if asset_col:
                for obj in asset_col.all_objects:
                    if obj.type == 'MESH':
                        # 🔥 [수정 완료] .split('.') 추가!
                        base_obj_name = obj.name.split('.')[0]
                        
                        if valid_mesh_names and base_obj_name in valid_mesh_names:
                            target_objs.append(obj)
                        elif not valid_mesh_names and base_obj_name.startswith(asset_name):
                            target_objs.append(obj)

            if not target_objs:
                print(f"[Fail] 원본과 일치하는 메쉬가 씬에 없음: {asset_name}")
                continue

            # (D) 모디파이어 안전 적용
            applied = False
            for obj in target_objs:
                mod = None
                for m in obj.modifiers:
                    if m.type == 'MESH_SEQUENCE_CACHE':
                        mod = m
                        break

                if not mod:
                    print(f"[SKIP] {obj.name}: MeshSequenceCache 모디파이어가 없어 캐시 경로만 갱신하지 못함")
                    continue

                cf = getattr(mod, 'cache_file', None)
                if not cf:
                    print(f"[SKIP] {obj.name}: 기존 cache_file 데이터블록이 없어 캐시 경로만 갱신하지 못함")
                    continue

                cf.name = exact_name
                cf.filepath = usd_path

                # USD Prim Path 보정: cache_file.object_paths에서 오브젝트 이름으로 검색
                try:
                    matched, old_path, new_path = _sync_modifier_object_path_from_cache(mod, obj.name, asset_name=asset_name)
                    if not matched:
                        print(f"[WARN] Prim Path 검색 실패: {obj.name} | 기존 경로 유지: {old_path}")
                except Exception as e:
                    print(f"[WARN] Prim Path 검색/적용 실패: {obj.name} ({e})")

                applied = True

                if applied:
                    updated_count += 1
                    print(f"[Success] {asset_name} 싱크 완료")

        self.report({'INFO'}, f"✅ 총 {updated_count}개 어셋 캐시 연결 완료")
        return {'FINISHED'}

################################################################
######################### Line Art #############################
################################################################
def get_latest_black_material():
    # "Black."으로 시작하는 재료 중 가장 최신의 것을 찾아 반환
    black_materials = [mat for mat in bpy.data.materials if mat.name.startswith("Black.")]
    black_materials.sort(key=lambda m: m.name, reverse=True)
    return black_materials[0] if black_materials else None


class LineArtGenerator(bpy.types.Operator):
    """Generate Line Art"""
    bl_idname = "object.line_art_generator"
    bl_label = "Generate Line Art"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        create_line_art_with_single_modifier()
        return {'FINISHED'}

class LineArtPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "Line Art Generator"
    bl_idname = "OBJECT_PT_line_art"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout
        layout.operator(LineArtGenerator.bl_idname)



################################################################
######################### Extras ###############################
################################################################



class SF_CleanupOrphansCombined(bpy.types.Operator):
    bl_idname = "sf.cleanup_orphans_combined1"
    bl_label = "Clean Up Orphans (Combined)"

    def execute(self, context):
        # 첫 번째 조건: 로컬 및 링크드 데이터 블록 모두 정리하지 않음
        bpy.ops.outliner.orphans_purge(do_recursive=True, do_local_ids=False, do_linked_ids=False)

        # 두 번째 조건: 로컬 데이터 블록만 정리
        bpy.ops.outliner.orphans_purge(do_recursive=True, do_local_ids=True, do_linked_ids=False)

        # 세 번째 조건: 링크드 데이터 블록만 정리
        bpy.ops.outliner.orphans_purge(do_recursive=True, do_local_ids=False, do_linked_ids=True)
        # node_group_linker = NodeGroupLinker("SF_paint", r"M:\e_utility\blender\shaders\sf_paint.blend")
        # node_group_linker.link_node_group()  # 노드 그룹 링크
        # node_group_linker.update_materials()  # 메터리얼 업데이트
        bpy.ops.object.delete_all_fake_users()
        return {'FINISHED'}
        
def get_latest_file_version(scene_number, cut_number):
    # 글로벌 변수 base_path를 직접 사용합니다.
    base_path = get_project_paths()
    full_path = os.path.join(base_path, "scenes", str(scene_number), str(cut_number), "ren")
    if not os.path.exists(full_path):
        return "No Render File"

    # 파일 목록 가져오기
    files = os.listdir(base_path)
    project_prefix = get_project_prefix()  # 현재 프로젝트의 식별자를 얻습니다.

    # 정규 표현식 패턴 설정
    pattern = re.compile(rf"{re.escape(project_prefix)}_" + re.escape(scene_number) + r"_" + re.escape(cut_number) + r"_ren_v(\d+)")

    versions = []

    for file in files:
        match = pattern.match(file)
        if match:
            versions.append(int(match.group(1)))

    if not versions:
        return "No Render File"

    latest_version = max(versions)
    return f"v{str(latest_version).zfill(3)}"
    

class SF_SaveRenderScene(bpy.types.Operator):
    bl_idname = "sf.save_render_scene"
    bl_label = "Save Render Scene"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        scene = context.scene
        my_tool = scene.my_tool
        self.scene_number = my_tool.scene_number if my_tool else 'default'
        self.cut_number = my_tool.cut_number if my_tool else 'default'
        base_path = get_project_paths()

        self.base_path = os.path.join(base_path, "scenes", self.scene_number, self.cut_number, "ren")
        project_prefix = get_project_prefix()  # 현재 프로젝트의 식별자를 얻습니다.
        self.file_name = f"{project_prefix}_{self.scene_number}_{self.cut_number}_ren_v000.blend"

        self.full_path = os.path.join(self.base_path, self.file_name)

        if os.path.exists(self.full_path):
            # 파일이 이미 존재하는 경우, 사용자에게 덮어쓰기 여부를 묻는다.
            return context.window_manager.invoke_confirm(self, event)
        else:
            return self.execute(context)

    def execute(self, context):
        # 디렉터리 생성 (경로가 존재하지 않는 경우)
        # os.makedirs(self.base_path, exist_ok=True)

        # 현재 씬을 self.full_path로 저장
        try:
            bpy.ops.wm.save_as_mainfile(filepath=self.full_path)
            self.report({'INFO'}, f"Scene saved to {self.full_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to save scene: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}




# 버전 정보를 유지하기 위한 전역 변수
current_version = 1

def update_version(context, increment):
    global current_version  # 전역 변수 사용 선언

    # 현재 씬의 기본 파일 경로, 최신 버전(+1), 그리고 기본 버전 가져오기
    original_path, new_path, default_version = get_base_filepath(context.scene)
    base_path = get_project_paths()
    
    if increment == -999:  # "Current" 버튼을 누른 경우
        current_version = int(default_version[1:])
    else:
        # "Dn" 버튼을 누르면 버전이 1이 될 때까지 계속 내려가고, "Up" 버튼을 누르면 버전이 계속 올라가는 것
        if increment < 0:  # "Dn" 버튼을 누른 경우
            current_version = max(1, current_version + increment)
        else:  # "Up" 버튼을 누른 경우
            current_version += increment

    new_version = f"v{str(current_version).zfill(3)}"

    # 파일 경로 업데이트
    context.scene.render.filepath = re.sub(default_version, new_version, original_path)

    # 씬 안의 모든 File Output 노드 경로 수정
    # Blender 4.x: scene.node_tree
    # Blender 5.x: scene.compositing_node_group
    tree = get_scene_compositor_tree(context.scene, create=False)
    if tree:
        for node in tree.nodes:
            if node.type == 'OUTPUT_FILE':
                node.base_path = re.sub(default_version, new_version, new_path)


class SF_OT_VersionOperator(bpy.types.Operator):
    bl_idname = "sf.version_operator"
    bl_label = "Version Operator"
    increment: bpy.props.IntProperty()

    def execute(self, context):
        update_version(context, self.increment)
        return {'FINISHED'}

# class IncrementalSaveOperator(Operator):
    # bl_idname = "scene.incremental_save"
    # bl_label = "Incremental Save"

    # def execute(self, context):
        # # 현재 파일의 경로와 이름을 가져옵니다.
        # current_filepath = bpy.data.filepath

        # # 'Incremental Save'를 수행합니다.
        # bpy.ops.wm.save_mainfile(filepath=current_filepath, incremental=True)

        # self.report({'INFO'}, "Incremental save completed.")
        # return {'FINISHED'}
        
class IncrementalSaveOperator(bpy.types.Operator):
    bl_idname = "scene.incremental_save"
    bl_label = "Incremental Save"

    def execute(self, context):
        scene_number = context.scene.my_tool.scene_number
        cut_number = context.scene.my_tool.cut_number
        base_path = get_project_paths()
        project_prefix = get_project_prefix()
        dir_path = os.path.join(base_path, "scenes", scene_number, cut_number, "ren")

        # 디렉토리 내 파일을 검색하여 가장 높은 버전의 파일을 찾습니다.
        blend_file = find_highest_version_file(dir_path, project_prefix, scene_number, cut_number)

        if blend_file:
            file_path = os.path.join(dir_path, blend_file)

            # 'Incremental Save'를 수행합니다.
            bpy.ops.wm.save_mainfile(filepath=file_path, incremental=True)

            self.report({'INFO'}, "Incremental save completed.")
        else:
            self.report({'ERROR'}, "No valid .blend file found for incremental save.")
        
        return {'FINISHED'}

def find_highest_version_file(dir_path, project_prefix, scene_number, cut_number):
    pattern = re.compile(rf"{re.escape(project_prefix)}_{re.escape(scene_number)}_{re.escape(cut_number)}_ren_v(\d+)\.blend$")
    highest_version = -1
    highest_version_file = None

    if os.path.exists(dir_path):
        for file_name in os.listdir(dir_path):
            if file_name.endswith(".blend"):  # .blend 확장자만 다룹니다.
                match = pattern.match(file_name)
                if match:
                    version = int(match.group(1))
                    if version > highest_version:
                        highest_version = version
                        highest_version_file = file_name

    return highest_version_file


ADDON_PATH = "M:/RND/SFtools/2023/render/rrRender.py"
ADDON_NAME = "rrRender"

class WM_OT_ReinstallAddon1(bpy.types.Operator):
    bl_label = "Reinstall Addon1"
    bl_idname = "wm.reinstall_addon_operator1"

    def execute(self, context):
        try:
            self.reinstall_addon(context)
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}

    def reinstall_addon(self, context):
        # Get the user scripts path for addons
        user_scripts_path = bpy.utils.user_resource('SCRIPTS')
        if not user_scripts_path:
            self.report({'ERROR'}, "User scripts path could not be determined.")
            raise Exception("User scripts path could not be determined.")
        
        # Define the destination path
        dest_path = os.path.join(user_scripts_path, "addons", os.path.basename(ADDON_PATH))

        # Copy the addon file
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy(ADDON_PATH, dest_path)
            self.report({'INFO'}, f"Successfully copied {os.path.basename(ADDON_PATH)} to {dest_path}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to copy {os.path.basename(ADDON_PATH)}: {e}")
            raise Exception(f"Failed to copy {os.path.basename(ADDON_PATH)}: {e}")

        # Reload the addon
        self.reload_addon(context)


    def reload_addon(self, context):
        if ADDON_NAME in bpy.context.preferences.addons:
            bpy.ops.preferences.addon_disable(module=ADDON_NAME)
            self.report({'INFO'}, f"Disabled {ADDON_NAME}")

        # Ensure the addon module is not loaded
        if ADDON_NAME in sys.modules:
            del sys.modules[ADDON_NAME]
            self.report({'INFO'}, f"Removed {ADDON_NAME} from sys.modules")

        # Load the addon module again
        try:
            bpy.ops.preferences.addon_enable(module=ADDON_NAME)
            self.report({'INFO'}, f"Enabled {ADDON_NAME}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to reload {ADDON_NAME}: {e}")
            raise Exception(f"Failed to reload {ADDON_NAME}: {e}")




# 프리셋 선택을 위한 EnumProperty 정의
def preset_items(self, context):
    # 'floor0F', 'floor1F', ...의 형식으로 이름 지정
    return [(f"floor{i}F", f"floor {i}F", f"Apply floor {i}F preset") for i in range(8)]

bpy.types.Scene.preset_selection = bpy.props.EnumProperty(
    name="Preset",
    description="Select a preset to apply",
    items=preset_items
)

class SF_OT_ApplyPreset(bpy.types.Operator):
    bl_label = "Apply Preset"
    bl_idname = "sf.apply_preset"

    preset_name: bpy.props.StringProperty()  # UI에서 선택된 프리셋 이름
    asset_names: bpy.props.StringProperty()  # 콤마로 구분된 선택된 어셋 이름들

    def execute(self, context):
        print("Starting execution of SF_OT_ApplyPreset")
        
        base_path = get_project_paths()
        asset_names_list = self.asset_names.split(',')  # 문자열을 리스트로 변환
        json_file_path = os.path.join(base_path, "_json", f"{self.preset_name}_preset.json")
        blend_file_path = ""  # 초기화
        self.delete_unused_worlds()
        print("json_file_path:", json_file_path)
        
        try:
            with open(json_file_path, 'r') as file:
                preset_data = json.load(file)
            blend_file_path = os.path.join(base_path, "assets", "bg", self.preset_name, "mod", f"{self.preset_name}.blend")
            print("Blend file path:", blend_file_path)
        except Exception as e:
            print(f"Error before setting blend_file_path: {e}")
            self.report({'ERROR'}, f"Failed to load preset data: {e}")
            return {'CANCELLED'}

        if not blend_file_path:
            print("blend_file_path not set due to previous error")
            return {'CANCELLED'}

        for asset_name in asset_names_list:
            light_object_name = f"{asset_name}_light"
            light_object = bpy.data.objects.get(light_object_name)
            if light_object:
                for prop_name, value in preset_data.get(asset_name, {}).items():
                    light_object[prop_name] = value
        # self.append_world(blend_file_path, f"{self.preset_name}_world", context)
        loaded_world = self.append_world(blend_file_path, f"{self.preset_name}_world", context)
        self.set_world_to_scene(loaded_world)
        self.delete_unused_worlds()
        _disable_default_view_layer(bpy.context.scene)
        
        return {'FINISHED'}

    def append_world(self, blend_path, world_name, context):
        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            if world_name in data_from.worlds:
                data_to.worlds = [world_name]
                print(f"World '{world_name}' loaded successfully from '{blend_path}'")
            else:
                print(f"World '{world_name}' not found in '{blend_path}'")
                return None
        return bpy.data.worlds.get(world_name)
        
    def set_world_to_scene(self, world):
        if world:
            bpy.context.scene.world = world
            print(f"World '{world.name}' is now set as the current scene world.")
        else:
            print("No world loaded to set to the scene.")
            
    def delete_unused_worlds(self):
        # 사용 중인 월드를 제외하고 모든 월드 삭제
        used_worlds = set(scene.world for scene in bpy.data.scenes if scene.world)
        all_worlds = set(bpy.data.worlds)
        # 사용 중이지 않은 월드만 삭제
        for world in all_worlds - used_worlds:
            bpy.data.worlds.remove(world, do_unlink=True)


# 렌더 세팅을 적용하는 연산자
class SF_OT_RenderSetting(bpy.types.Operator):
    bl_idname = "scene.render_setting"
    bl_label = "Apply Render Setting"

    mode: bpy.props.StringProperty()  # 'Preview' 또는 'Best' 설정을 위한 매개변수

    def execute(self, context):
        sc = context.scene
        engine = sc.render.engine

        # ------------------------------
        # EEVEE & EEVEE Next
        # ------------------------------
        if engine in {'BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'}:
            ee = getattr(sc, "eevee", None)

            if self.mode == 'Preview':
                try:
                    ee.shadow_cube_resolution = 4096
                    ee.use_shadow_high_bitdepth = False
                    sc.render.use_high_quality_normals = False
                    ee.taa_samples = 16
                    ee.gtao_quality = 1
                except AttributeError:
                    pass

            elif self.mode == 'Best':
                try:
                    # bpy.ops.sf.subdivide_class()
                    ee.shadow_cube_resolution = 4096
                    ee.use_shadow_high_bitdepth = True
                    sc.render.use_high_quality_normals = False
                    ee.taa_samples = 30
                    # bpy.ops.sf.subdivide_class()
                    ee.taa_render_samples = 30
                    ee.use_overscan = True
                    ee.overscan_size = 20
                    ee.ssr_border_fade = 0.001
                    ee.gtao_quality = 1
                except AttributeError:
                    pass

            else:
                self.report({'ERROR'}, f"Unknown mode: {self.mode}")
                return {'CANCELLED'}

        # ------------------------------
        # Cycles
        # ------------------------------
        elif engine == 'CYCLES':
            cy = getattr(sc, "cycles", None)

            if self.mode == 'Preview':
                try:
                    cy.samples = 64
                    cy.use_adaptive_sampling = True
                    cy.use_preview_denoising = True
                except AttributeError:
                    pass

            elif self.mode == 'Best':
                try:
                    cy.samples = 64
                    cy.use_adaptive_sampling = True
                    cy.use_preview_denoising = True
                except AttributeError:
                    pass

            else:
                self.report({'ERROR'}, f"Unknown mode: {self.mode}")
                return {'CANCELLED'}

        # ------------------------------
        # Other Engine
        # ------------------------------
        else:
            self.report({'WARNING'}, f"지원하지 않는 렌더 엔진: {engine}")
            return {'CANCELLED'}

        return {'FINISHED'}



  
class SF_OT_RefreshDriverDependencies(bpy.types.Operator):
    """Refresh Driver Dependencies"""
    bl_idname = "scene.refresh_driver_dependencies"
    bl_label = "Refresh Driver Dependencies"

    def execute(self, context):
        # 강제로 의존성 그래프 업데이트
        bpy.context.view_layer.update()
        self.report({'INFO'}, "Driver dependencies refreshed.")
        # bpy.ops.object.sf_add_properties_and_link1()
        # bpy.ops.object.sf_link_character_lights1()
        bpy.ops.object.link_rim_to_node1()
        # bpy.ops.sf.updatelightposition_class()
        return {'FINISHED'}


class SF_OT_GetSelectedAssetsOperator(bpy.types.Operator):
    bl_idname = "sf.get_selected_assets_operator"
    bl_label = "Get Selected Assets"

    @classmethod
    def poll(cls, context):
        return context.scene.sf_file_categories is not None

    def execute(self, context):
        all_assets = []
        ch_assets = []
        bg_assets = []
        prop_assets = []

        for category in context.scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    all_assets.append(item.name)
                    if category.name == 'ch':
                        ch_assets.append(item.name)
                    elif category.name == 'bg':
                        bg_assets.append(item.name)
                    elif category.name == 'prop':
                        prop_assets.append(item.name)


        # 필요에 따라 정보를 다른 방식으로 사용할 수 있습니다.
        return {'FINISHED'}

class SF_OT_SetStaticBG(bpy.types.Operator):
    bl_idname = "sf.set_static_bg"
    bl_label = "Set Static Background"

    def execute(self, context):
        scene = context.scene
        bg_vl = scene.view_layers.get('bg_vl')
        if bg_vl:
            # Ensure animation data exists
            if scene.animation_data and scene.animation_data.action:
                # Clear existing keyframes if any
                fcurves = [fcurve for fcurve in scene.animation_data.action.fcurves if fcurve.data_path == "view_layers[\"bg_vl\"].use"]
                for fcurve in fcurves:
                    scene.animation_data.action.fcurves.remove(fcurve)

            # Set the 'use' property to True
            bg_vl.use = True
            scene.frame_step = 1
        else:
            self.report({'WARNING'}, "ViewLayer 'bg_vl' not found")

        return {'FINISHED'}


class SF_OT_SetMovingBG(bpy.types.Operator):
    bl_idname = "sf.set_moving_bg"
    bl_label = "Set Moving Background"

    def execute(self, context):
        scene = context.scene
        bg_vl = scene.view_layers.get('bg_vl')
        if bg_vl:
            # Ensure animation data exists
            if scene.animation_data and scene.animation_data.action:
                # Clear existing keyframes if any
                fcurves = [fcurve for fcurve in scene.animation_data.action.fcurves if fcurve.data_path == "view_layers[\"bg_vl\"].use"]
                for fcurve in fcurves:
                    scene.animation_data.action.fcurves.remove(fcurve)

            # Set the 'use' property to True
            bg_vl.use = True
            scene.frame_step = 1
        else:
            self.report({'WARNING'}, "ViewLayer 'bg_vl' not found")

        return {'FINISHED'}

class SF_OT_SetViewLayerMode(bpy.types.Operator):
    bl_idname = "sf.set_view_layer_mode"
    bl_label = "Set View Layer Mode"
    
    mode: bpy.props.StringProperty()
    
    def add_suffix_to_filepath(self, suffix):
        scene = bpy.context.scene
        filepath = scene.render.filepath

        # 이미 접미사가 있는지 확인하고 제거
        filepath = filepath.replace("ch_", "").replace("bg_", "")

        # 새로운 접미사 추가
        filepath += suffix

        scene.render.filepath = filepath
    
    def execute(self, context):
        if self.mode == "ch_only":
            self.set_ch_only(context)
        elif self.mode == "bg_only":
            self.set_bg_only(context)
        elif self.mode == "all":
            self.set_all(context)
        elif self.mode == "viewlayer":
            self.set_viewlayer(context)
        
        return {'FINISHED'}
    
    def set_ch_only(self, context):
        scene = context.scene
        for vl in scene.view_layers:
            vl.use = vl.name.startswith('ch')
        scene.frame_step = 1
        self.disable_specific_view_layer(context, 'ViewLayer')
        self.add_suffix_to_filepath("ch_")
        
    def set_bg_only(self, context):
        scene = context.scene
        for vl in scene.view_layers:
            vl.use = not vl.name.startswith('ch')
        scene.frame_step = 1
        self.disable_specific_view_layer(context, 'ViewLayer')
        self.add_suffix_to_filepath("bg_")
        
    def set_all(self, context):
        scene = context.scene
        for vl in scene.view_layers:
            vl.use = True
        scene.frame_step = 1
        self.disable_specific_view_layer(context, 'ViewLayer')

        filepath = scene.render.filepath
        # "ch_" 또는 "bg_" 접미사가 있는 경우 제거
        if filepath.endswith("ch_") or filepath.endswith("bg_"):
            filepath = filepath[:-3]
        scene.render.filepath = filepath
        
    def set_viewlayer(self, context):
        scene = context.scene
        for vl in scene.view_layers:
            # 'ViewLayer' 뷰 레이어만 사용하고, 나머지는 사용하지 않도록 설정
            if vl.name == 'ViewLayer':
                vl.use = True
            else:
                vl.use = False
        scene.frame_step = 1

        filepath = scene.render.filepath
        # "ch_" 또는 "bg_" 접미사가 있는 경우 제거
        if filepath.endswith("ch_") or filepath.endswith("bg_"):
            filepath = filepath[:-3]
        scene.render.filepath = filepath

        
    def disable_specific_view_layer(self, context, layer_name):
        vl = context.scene.view_layers.get(layer_name)
        if vl:
            vl.use = False
            
import subprocess

def get_deadline_command():
    """이 함수는 Deadline의 명령 실행 파일 경로를 찾습니다."""
    deadline_bin = os.getenv('DEADLINE_PATH', '')
    if not deadline_bin and os.path.exists("/Users/Shared/Thinkbox/DEADLINE_PATH"):
        with open("/Users/Shared/Thinkbox/DEADLINE_PATH") as f:
            deadline_bin = f.read().strip()
    return os.path.join(deadline_bin, "deadlinecommand")


class SubmitBlenderToDeadline(bpy.types.Operator):
    """Blender 작업을 Deadline에 제출합니다."""
    bl_idname = "wm.submit_blender_to_deadline"
    bl_label = "Submit Blender to Deadline"

    def execute(self, context):
        import os, subprocess
        sc = context.scene

        try:
            bpy.ops.sf.set_light_bounces()
            print("[SUBMIT] SF_OT_SetLightBounces 실행 완료")
        except Exception as e:
            print(f"[SUBMIT ERROR] LightBounces 실행 실패: {e}")

        # --- 렌더링 설정 ---
        bpy.ops.file.make_paths_absolute()
        bpy.ops.scene.render_setting(mode='Best')

        # --- 씬 파일/프레임 범위/출력 경로/스레드 수 ---
        scene_file = bpy.data.filepath
        frame_range = f"{sc.frame_start}-{sc.frame_end}"
        output_path = sc.render.filepath
        threads = sc.render.threads if sc.render.threads_mode != 'AUTO' else 0
        platform = str(bpy.app.build_platform)

        # --- 외부 라이브러리 경로 치환 ---
        bpy.ops.object.replace_botaniq_library_path()
        bpy.ops.object.replace_sanctus_library_path()

        # --- Blender 버전에 따른 드롭다운 선택 ---
        major, minor, patch = bpy.app.version
        blender_version_str = f"{major}.{minor}"

        version_string = str(bpy.app.version_string).lower()
        build_info_raw = bpy.app.build_branch
        if isinstance(build_info_raw, bytes):
            build_info = build_info_raw.decode(errors="ignore").lower()
        else:
            build_info = str(build_info_raw).lower()

        if "goo" in version_string or "goo" in build_info:
            blender_version = "GOO"
        # elif "ssgi" in version_string or "ssgi" in build_info:
            # blender_version = "SSGI"
        # elif blender_version_str == "4.2":
            # blender_version = "42"
        elif blender_version_str == "4.3":
            blender_version = "43"
        elif blender_version_str == "4.5":
            blender_version = "45"
        else:
            blender_version = "43"  # fallback

        print(f"[INFO] Blender 실행 버전 감지: {bpy.app.version_string} ({build_info}) → Deadline 드롭다운 '{blender_version}' 선택")

        # --- Deadline 제출 인자 구성 ---
        script_file = self.get_repository_file_path("scripts/Submission/BlenderSubmission.py")

        args = [
            get_deadline_command(),
            "-ExecuteScript",
            script_file,
            scene_file,
            frame_range,
            output_path,
            str(threads),
            platform,
            blender_version
        ]

        print(f"Submitting to Deadline with Blender version: {blender_version}")
        subprocess.Popen(args)

        # --- 씬 저장 ---
        bpy.ops.wm.save_mainfile()
        return {'FINISHED'}

    def get_repository_file_path(self, subdir):
        """Deadline 리포지토리에서 특정 파일의 경로를 가져옵니다."""
        import subprocess
        args = [get_deadline_command(), "-GetRepositoryFilePath", subdir]
        output = subprocess.check_output(args).decode().strip()
        return output.replace("\\", "/")




def camera_has_movement(camera):
    if not camera or not camera.animation_data or not camera.animation_data.action:
        return False

    has_movement = False
    loc_fcurves = [camera.animation_data.action.fcurves.find(data_path) for data_path in ("location", "rotation_euler", "rotation_quaternion")]
    loc_fcurves = [fcurve for fcurve in loc_fcurves if fcurve]

    # 각 변환 키프레임을 비교하여 실제 움직임이 있는지 확인
    for fcurve in loc_fcurves:
        if len(fcurve.keyframe_points) > 1:
            keyframe_values = [point.co[1] for point in fcurve.keyframe_points]
            if len(set(keyframe_values)) > 1:  # 중복된 값을 제외하고 값이 하나 이상이면 움직임이 있다
                has_movement = True
                break

    return has_movement

class CameraMovementFrameRangeOperator(bpy.types.Operator):
    bl_idname = "frame.set_camera_movement_frame_range"
    bl_label = "Set Camera Movement Frame Range"

    def execute(self, context):
        scene = context.scene
        camera = scene.camera

        if camera_has_movement(camera):
            # 카메라의 움직임이 있는 경우
            loc_fcurves = [camera.animation_data.action.fcurves.find(data_path) for data_path in ("location", "rotation_euler", "rotation_quaternion")]
            loc_fcurves = [fcurve for fcurve in loc_fcurves if fcurve]

            # 움직임이 시작되는 첫 번째 프레임 찾기
            start_frame = min([min(fcurve.keyframe_points, key=lambda point: point.co[0]).co[0] for fcurve in loc_fcurves])

            # 움직임이 끝나는 마지막 프레임 찾기
            end_frame = max([max(fcurve.keyframe_points, key=lambda point: point.co[0]).co[0] for fcurve in loc_fcurves])

            # 프레임 레인지 설정 (부동 소수점을 정수로 변환)
            scene.frame_start = int(start_frame)
            scene.frame_end = int(end_frame)
            print("Camera movement frame range set: {} - {}".format(int(start_frame), int(end_frame)))
        else:
            print("Camera has no movement.")

        return {'FINISHED'}


class FrameRangeOperator(bpy.types.Operator):
    bl_idname = "frame.range_operator"
    bl_label = "Frame Range Operator"

    option: bpy.props.StringProperty(default="FULL")

    def set_frame_range_from_json(self, json_file_path):
        if os.path.exists(json_file_path):
            with open(json_file_path, 'r') as json_file:
                camera_data = json.load(json_file)
                scene = bpy.context.scene
                scene.frame_start = int(camera_data.get('minTime', scene.frame_start))
                scene.frame_end = int(camera_data.get('maxTime', scene.frame_end))
                print("Frame range set from JSON: {} - {}".format(scene.frame_start, scene.frame_end))
        else:
            print("JSON file not found.")

    def set_current_frame_range(self):
        scene = bpy.context.scene
        scene.frame_start = scene.frame_current
        scene.frame_end = scene.frame_current
        print("Frame range set to current frame ({})".format(scene.frame_current))

    def execute(self, context):
        scene = context.scene
        my_tool = context.scene.my_tool
        scene_number = my_tool.scene_number
        cut_number = my_tool.cut_number
        base_path = get_project_paths()
        project_prefix = get_project_prefix()  # 현재 프로젝트의 식별자를 얻습니다.

        # JSON 파일 이름 설정
        json_file_name = f"{project_prefix}_{scene_number}_{cut_number}_camera_data.json"

        # JSON 파일 전체 경로 설정
        full_json_path = os.path.join(os.path.join(base_path, "scenes", scene_number, cut_number, "ren", "cache"), json_file_name)

        if self.option == "FULL":
            self.set_frame_range_from_json(full_json_path)
        elif self.option == "CURRENT":
            self.set_current_frame_range()

        return {'FINISHED'}

class SimpleSceneProps(bpy.types.PropertyGroup):
    # 드롭다운 메뉴를 위한 EnumProperty 설정, 순서 변경
    mode_items = [
        ('all', "BG + CH", "", 'PLAY', 0),
        ('ch_only', "Ch Only", "", 'OUTLINER_OB_ARMATURE', 1),
        ('bg_only', "Bg Only", "", 'FILE_IMAGE', 2),
        ('viewlayer', "ViewLayer", "", 'RENDERLAYERS', 3),
    ]
    mode: bpy.props.EnumProperty(
        name="Mode",
        items=mode_items,
        default='all',
        update=lambda self, context: self.update_mode()
    )

    def update_mode(self):
        mode = self.mode
        print(f"Mode set to: {mode}")
        # 해당 모드에 대한 실제 로직을 호출합니다.
        bpy.ops.sf.set_view_layer_mode(mode=mode)

######################################################################
###########################Light Mask    #############################
######################################################################

class OBJECT_OT_apply_light_mask(bpy.types.Operator):
    bl_idname = "object.apply_light_mask"
    bl_label = "Apply Light Mask"
    
    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                self.create_light_mask(obj, "lightmask_col", "MI_lightmask")
            else:
                print(f"Skipped {obj.name}: Not a mesh object.")
        
        if "lightmask_vl" not in bpy.context.scene.view_layers:
            self.create_view_layer("ViewLayer", "lightmask_vl", "lightmask_col")
        
        self.setup_lightmask_view_layer("lightmask_vl", "lightmask_col")
        self.deactivate_lightmask_col_in_other_layers("lightmask_vl", "lightmask_col")
        return {'FINISHED'}
    
    def create_light_mask(self, obj, collection_name, material_name):
        light_mask_name = obj.name + "_lightmask"
        if light_mask_name in bpy.data.objects:
            print("Light mask object already exists.")
            return
        
        obj_copy = obj.copy()
        obj_copy.data = obj.data.copy()
        obj_copy.name = light_mask_name
        
        self.disable_solidify_modifier(obj_copy)
        self.apply_material(obj_copy, material_name)
        
        self.setup_collection(collection_name)
        collection = bpy.data.collections.get(collection_name)
        if obj_copy.name not in collection.objects:
            collection.objects.link(obj_copy)

        self.create_lights(collection_name)

    def disable_solidify_modifier(self, obj):
        for mod in obj.modifiers:
            if mod.type == 'SOLIDIFY':
                mod.show_render = False
                mod.show_viewport = False

    def apply_material(self, obj, material_name):
        # Remove all existing materials
        obj.data.materials.clear()

        # Get or create the material
        mat = bpy.data.materials.get(material_name)
        if not mat:
            mat = self.create_material(material_name)

        # Assign the material
        obj.data.materials.append(mat)

    def create_material(self, material_name):
        # Load the material from an external Blender file
        filepath = "M:/RND/SFtools/2025/lookdev/blend/ldvLight_v03.blend"
        material_path = os.path.join(filepath, "Material", material_name)
        
        # Check if the material already exists in the current scene
        mat = bpy.data.materials.get(material_name)
        if mat:
            print(f"Material {material_name} already exists in the scene.")
            return mat
        
        # Append the material from the external file if it's not already loaded
        if material_name not in bpy.data.materials:
            try:
                bpy.ops.wm.append(filepath=material_path, directory=os.path.join(filepath, "Material"), filename=material_name)
                mat = bpy.data.materials.get(material_name)
                if mat:
                    print(f"Successfully appended material: {material_name}")
                else:
                    print(f"Failed to append material {material_name}")
                    return None
            except Exception as e:
                print(f"Error appending material {material_name}: {e}")
                return None
        
        return mat

    def create_lights(self, collection_name):
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(collection)
        
        light_properties = [
            ("lgtRed", (1.0, 0.0, 0.0)),
            ("lgtGreen", (0.0, 1.0, 0.0)),
            ("lgtBlue", (0.0, 0.0, 1.0))
        ]
        
        for light_name, color in light_properties:
            if light_name not in bpy.data.objects:
                light_data = bpy.data.lights.new(name=light_name, type='SUN')
                light_object = bpy.data.objects.new(name=light_name, object_data=light_data)
                collection.objects.link(light_object)
                light_data.color = color
                light_data.energy = 3  # Set power to 100
                light_data.specular_factor = 0
                light_data.volume_factor = 0
                light_data.shadow_soft_size = 0.15  # Set radius to 15 cm
                light_data.cutoff_distance = 1.0  # Set custom distance to 100 cm
                light_data.use_shadow = True
                light_data.shadow_cascade_max_distance = 8
                light_data.shadow_buffer_bias = 0.03
                light_data.use_contact_shadow = False
        # bpy.data.objects["lgtRed"].hide_viewport = False
        # bpy.data.objects["lgtRed"].hide_render = False

        # bpy.data.objects["lgtGreen"].hide_viewport = True
        # bpy.data.objects["lgtGreen"].hide_render = True

        # bpy.data.objects["lgtBlue"].hide_viewport = True
        # bpy.data.objects["lgtBlue"].hide_render = True

    def setup_collection(self, collection_name):
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(collection)

    def create_view_layer(self, base_layer_name, new_layer_name, collection_name):
        base_layer = bpy.context.view_layer
        bpy.ops.scene.view_layer_add()
        new_layer = bpy.context.view_layer
        new_layer.name = new_layer_name

        for layer_collection in new_layer.layer_collection.children:
            if layer_collection.name != collection_name:
                layer_collection.exclude = True
            else:
                layer_collection.exclude = False

    def setup_lightmask_view_layer(self, light_mask_layer_name, collection_name):
        for scene_layer in bpy.context.scene.view_layers:
            if scene_layer.name == light_mask_layer_name:
                for layer_collection in scene_layer.layer_collection.children:
                    if layer_collection.name != collection_name:
                        layer_collection.exclude = True
                    else:
                        layer_collection.exclude = False

    def deactivate_lightmask_col_in_other_layers(self, light_mask_layer_name, collection_name):
        for scene_layer in bpy.context.scene.view_layers:
            if scene_layer.name != light_mask_layer_name:
                for layer_collection in scene_layer.layer_collection.children:
                    if layer_collection.name == collection_name:
                        layer_collection.exclude = True

import bpy
import os

class OBJECT_OT_update_light_mask(bpy.types.Operator):
    bl_idname = "object.update_light_mask"
    bl_label = "Update Light Mask"
    
    def execute(self, context):
        light_material_name = "MI_lightmask"

        # Always create or replace the existing material
        light_mat = self.create_new_material(light_material_name)

        if not light_mat:
            self.report({'ERROR'}, "Could not find or load the material.")
            return {'CANCELLED'}

        # Replace the materials for all selected mesh objects
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                self.replace_matching_materials(obj, light_material_name, light_mat)
            else:
                print(f"Skipped {obj.name}: Not a mesh object.")
        
        print("Light mask material update complete.")
        return {'FINISHED'}

    def create_new_material(self, material_name):
        """
        Always append a new material from the external Blender file and return it.
        """
        filepath = os.path.normpath(r"M:\RND\SFtools\2025\lookdev\blend\ldvLight_v03.blend")
        try:
            # Track existing materials
            existing_materials = set(bpy.data.materials.keys())

            # Append the material
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                matching_materials = [mat for mat in data_from.materials if mat.lower() == material_name.lower()]
                if matching_materials:
                    data_to.materials = [matching_materials[0]]
                    print(f"Appending material: {matching_materials[0]}")
                else:
                    print(f"Error: Material '{material_name}' not found in the file.")
                    return None

            # Find newly appended material
            for mat_name in bpy.data.materials.keys():
                if mat_name not in existing_materials:
                    mat = bpy.data.materials[mat_name]
                    print(f"Newly appended material: {mat.name}")
                    return mat

        except Exception as e:
            print(f"Error appending material {material_name}: {e}")
            return None

        print("Failed to append or identify the new material.")
        return None

    def replace_matching_materials(self, obj, material_prefix, new_material):
        """
        Replace materials in the given object that start with the specified prefix.
        """
        for slot in obj.material_slots:
            if slot.material and slot.material.name.startswith(material_prefix):
                print(f"Replacing material {slot.material.name} with {new_material.name} on object {obj.name}")
                slot.material = new_material


class OBJECT_OT_remove_light_mask(bpy.types.Operator):
    bl_idname = "object.remove_light_mask"
    bl_label = "Remove Light Mask"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        selected_objects = context.selected_objects

        # Remove "_lightmask" objects from the selected objects
        for obj in selected_objects:
            if obj.name.endswith("_lightmask"):
                obj_name = obj.name  # Store the name before deletion
                bpy.data.objects.remove(obj)
                print(f"Removed light mask object: {obj_name}")

        # Check and remove the lightmask collection if it's empty
        target_collection_name = "lightmask_col"
        target_collection = bpy.data.collections.get(target_collection_name)
        
        if target_collection:
            # Clean up light group settings for lights in the collection
            for obj in list(target_collection.objects):  # Use a list to avoid modification during iteration
                if obj.type == 'LIGHT':
                    obj.data.light_groups.use_default = True  # Enable default light groups
                    obj.data.light_groups.groups.clear()  # Clear all light groups
                else:
                    print(f"Object '{obj.name}' is not a light.")

            # Remove the collection if empty
            if not target_collection.objects:
                bpy.data.collections.remove(target_collection)
                print(f"Removed empty collection: {target_collection_name}")
        else:
            print(f"Collection '{target_collection_name}' not found.")

        return {'FINISHED'}


class OBJECT_OT_make_shared_unique_material(bpy.types.Operator):
    bl_idname = "object.make_shared_unique_material"
    bl_label = "Make Shared Unique Material"
    bl_description = "Create a single-user copy of the material and assign it to selected objects"

    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']

        if not selected_objects:
            self.report({'WARNING'}, "No mesh objects selected!")
            return {'CANCELLED'}

        # Check the first selected object's material
        if not selected_objects[0].data.materials:
            self.report({'WARNING'}, "Selected objects have no materials!")
            return {'CANCELLED'}

        # Use the material of the first object as a base
        base_material = selected_objects[0].data.materials[0]

        # Create a single-user copy of the material
        unique_material = base_material.copy()
        unique_material.name = f"{base_material.name}_unique"

        # Assign the unique material to all selected objects
        for obj in selected_objects:
            if obj.data.materials:
                obj.data.materials.clear()  # Remove existing materials
            obj.data.materials.append(unique_material)

        self.report({'INFO'}, f"Unique material '{unique_material.name}' assigned to {len(selected_objects)} objects.")
        return {'FINISHED'}

######################################################################
###########################Caustics Mask #############################
######################################################################
class OBJECT_OT_apply_caustics_mask(bpy.types.Operator):
    bl_idname = "object.apply_caustics_mask"
    bl_label = "Apply Caustics Mask"
    
    def execute(self, context):
        # 컬렉션을 먼저 설정합니다
        self.setup_collection("caustic_col")

        # 그 다음 메터리얼을 생성합니다
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                self.create_caustics_mask(obj, "caustic_col", "MI_causticsmask")
            else:
                print(f"Skipped {obj.name}: Not a mesh object.")
        
        # 마지막으로 뷰 레이어를 설정합니다
        if "caustic_vl" not in bpy.context.scene.view_layers:
            self.create_view_layer("ViewLayer", "caustic_vl", "caustic_col")
        
        self.setup_caustics_view_layer("caustic_vl", "caustic_col")
        self.deactivate_caustic_col_in_other_layers("caustic_vl", "caustic_col")
        
        return {'FINISHED'}
    
    def create_caustics_mask(self, obj, collection_name, material_name):
        caustics_mask_name = obj.name + "_cMask"
        if caustics_mask_name in bpy.data.objects:
            print("Caustics mask object already exists.")
            return
        
        obj_copy = obj.copy()
        obj_copy.data = obj.data.copy()
        obj_copy.name = caustics_mask_name
        
        self.disable_solidify_modifier(obj_copy)
        self.apply_material(obj_copy, material_name)
        
        self.setup_collection(collection_name)
        collection = bpy.data.collections.get(collection_name)
        if obj_copy.name not in collection.objects:
            collection.objects.link(obj_copy)

    def disable_solidify_modifier(self, obj):
        for mod in obj.modifiers:
            if mod.type == 'SOLIDIFY':
                mod.show_render = False
                mod.show_viewport = False

    def apply_material(self, obj, material_name):
        # Remove all existing materials
        obj.data.materials.clear()

        # Get or create the material
        mat = bpy.data.materials.get(material_name)
        if not mat:
            mat = self.create_material(material_name)

        # Assign the material
        obj.data.materials.append(mat)

        # Add Caustics_Range to caustic_col collection
        caustics_range_obj = bpy.data.objects.get("Caustics_Range")
        collection = bpy.data.collections.get("caustic_col")
        if caustics_range_obj and collection:
            if caustics_range_obj.name not in collection.objects:
                collection.objects.link(caustics_range_obj)


    def create_material(self, material_name):
        mat = bpy.data.materials.new(name=material_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        nodes.clear()

        # Append the caustics shader node group from external blend file
        try:
            bpy.ops.wm.append(
                filepath="T:/assets/library/shader/floor2F_Water.blend",
                directory="T:/assets/library/shader/floor2F_Water.blend/NodeTree",
                filename="SF_CausticsShader"
            )
            caustics_shader = nodes.new(type='ShaderNodeGroup')
            caustics_shader.node_tree = bpy.data.node_groups['SF_CausticsShader']

            # Create material output node
            material_output = nodes.new(type='ShaderNodeOutputMaterial')

            # Set node positions
            caustics_shader.location = (0, 0)
            material_output.location = (200, 0)

            # Link caustics shader directly to the material output
            links.new(caustics_shader.outputs['Shader'], material_output.inputs['Surface'])

            # Set caustics shader properties
            caustics_shader.inputs['Strength'].default_value = 8
            caustics_shader.inputs['Scale'].default_value = 0.35
        except KeyError:
            self.report({'ERROR'}, "SF_CausticsShader node group not found in the specified blend file.")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to append the node group: {str(e)}")

        return mat

    def setup_collection(self, collection_name):
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(collection)

    def create_view_layer(self, base_layer_name, new_layer_name, collection_name):
        base_layer = bpy.context.view_layer
        bpy.ops.scene.view_layer_add()
        new_layer = bpy.context.view_layer
        new_layer.name = new_layer_name

        for layer_collection in new_layer.layer_collection.children:
            if layer_collection.name != collection_name:
                layer_collection.exclude = True
            else:
                layer_collection.exclude = False

    def setup_caustics_view_layer(self, caustics_mask_layer_name, collection_name):
        for scene_layer in bpy.context.scene.view_layers:
            if scene_layer.name == caustics_mask_layer_name:
                for layer_collection in scene_layer.layer_collection.children:
                    if layer_collection.name != collection_name:
                        layer_collection.exclude = True
                    else:
                        layer_collection.exclude = False

    def deactivate_caustic_col_in_other_layers(self, caustics_mask_layer_name, collection_name):
        for scene_layer in bpy.context.scene.view_layers:
            if scene_layer.name != caustics_mask_layer_name:
                for layer_collection in scene_layer.layer_collection.children:
                    if layer_collection.name == collection_name:
                        layer_collection.exclude = True


class OBJECT_OT_remove_caustics_mask(bpy.types.Operator):
    bl_idname = "object.remove_caustics_mask"
    bl_label = "Remove Caustics Mask"

    def execute(self, context):
        for obj in context.selected_objects:
            if obj:
                if obj.name.endswith("_cMask") or obj.name.endswith(".001"):
                    bpy.data.objects.remove(obj)
        
        # Check and remove the caustics collection if it's empty
        target_collection_name = "caustic_col"
        target_collection = bpy.data.collections.get(target_collection_name)
        
        if target_collection:
            for obj in target_collection.objects:
                if obj.type == 'LIGHT':
                    obj.data.light_groups.use_default = True  # Enable use of default light group
                    obj.data.light_groups.groups.clear()  # Remove all light groups
                else:
                    print(f"Object '{obj.name}' is not a light.")
            
            if not target_collection.objects:
                bpy.data.collections.remove(target_collection)
                print(f"Collection '{target_collection_name}' removed.")
        else:
            print(f"Collection '{target_collection_name}' not found.")

        # Check if caustic_col is removed and if so, remove the caustics_vl view layer
        if not bpy.data.collections.get(target_collection_name):
            view_layer_name = "caustics_vl"
            base_layer_name = "ViewLayer"
            bpy.context.window.view_layer = bpy.context.scene.view_layers.get(base_layer_name)
            for view_layer in bpy.context.scene.view_layers:
                if view_layer.name == view_layer_name:
                    bpy.context.scene.view_layers.remove(view_layer)
                    print(f"View layer '{view_layer_name}' removed.")
                    break
        
        return {'FINISHED'}




######################################################################
###########################Shadow Catcher#############################
######################################################################

class OBJECT_OT_apply_shadow_catcher(bpy.types.Operator):
    bl_idname = "object.apply_shadow_catcher"
    bl_label = "Apply Shadow Catcher"
    
    def execute(self, context):
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                self.create_shadow_catcher(obj.name, "ch_shadow_col", "MI_shadow")
            else:
                print(f"Skipped {obj.name}: Not a mesh object.")
        return {'FINISHED'}
    
    def create_shadow_catcher(self, obj_name, collection_name, material_name):
        obj = bpy.data.objects.get(obj_name)
        if not obj:
            print("Object not found.")
            return
        
        shadow_name = obj_name + "_shadow"
        if shadow_name in bpy.data.objects:
            print("Shadow object already exists.")
            return
        
        obj_copy = obj.copy()
        obj_copy.data = obj.data.copy()
        obj_copy.name = shadow_name
        
        mat = self.create_material(material_name)
        if not obj_copy.material_slots:
            obj_copy.data.materials.append(mat)
        else:
            obj_copy.material_slots[0].material = mat
        
        self.setup_collection(collection_name, bpy.context.scene.view_layers)
        collection = bpy.data.collections.get(collection_name)
        if obj_copy.name not in collection.objects:
            collection.objects.link(obj_copy)

    # def create_material(self, material_name):
        # mat = bpy.data.materials.get(material_name)
        # if not mat:
            # mat = bpy.data.materials.new(name=material_name)
            # mat.use_nodes = True
            # nodes = mat.node_tree.nodes
            # links = mat.node_tree.links
            # nodes.clear()

            # trans_bsdf = nodes.new(type='ShaderNodeBsdfTransparent')
            # trans_bsdf.location = (-300, 0)
            # diffuse_bsdf = nodes.new(type='ShaderNodeBsdfDiffuse')
            # diffuse_bsdf.location = (-600, 200)
            # shader_to_rgb = nodes.new(type='ShaderNodeShaderToRGB')
            # shader_to_rgb.location = (-300, 200)
            # color_ramp = nodes.new(type='ShaderNodeValToRGB')
            # color_ramp.location = (0, 200)
            # mix_shader = nodes.new(type='ShaderNodeMixShader')
            # mix_shader.location = (300, 0)
            # material_output = nodes.new(type='ShaderNodeOutputMaterial')
            # material_output.location = (600, 0)
            # shader_info = nodes.new(type='ShaderNodeShaderInfo')
            # shader_info.location = (-600, -200)

            # diffuse_bsdf.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
            # color_ramp.color_ramp.elements[0].position = 0.845
            # color_ramp.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
            # color_ramp.color_ramp.elements[1].position = 1.0
            # color_ramp.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)

            # links.new(shader_info.outputs['Cast Shadow'], color_ramp.inputs['Fac'])
            # links.new(color_ramp.outputs['Color'], mix_shader.inputs['Fac'])
            # links.new(trans_bsdf.outputs['BSDF'], mix_shader.inputs[1])
            # links.new(mix_shader.outputs['Shader'], material_output.inputs['Surface'])

            # mat.blend_method = 'BLEND'
        
        # return mat
    def create_material(self, material_name):
        # Load the material from an external Blender file
        filepath = "M:/RND/SFtools/2025/lookdev/blend/ldvLight_v03.blend"
        material_name = "MI_shadow"
        
        # Check if the material already exists in the current scene
        mat = bpy.data.materials.get(material_name)
        if mat:
            print(f"Material {material_name} already exists in the scene.")
            return mat
        
        # Append the material from the external file if it's not already loaded
        if material_name not in bpy.data.materials:
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                if material_name in data_from.materials:
                    data_to.materials = [material_name]
                else:
                    print(f"Material {material_name} not found in {filepath}")
                    return None
        
        # Return the material
        mat = bpy.data.materials.get(material_name)
        if not mat:
            print(f"Failed to load material {material_name}")
            return None
        
        return mat

    def setup_collection(self, collection_name, view_layers):
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            collection = bpy.data.collections.new(collection_name)
            bpy.context.scene.collection.children.link(collection)

        for layer in view_layers:
            layer_collection = layer.layer_collection.children.get(collection_name)
            if layer_collection is None:
                layer_collection = layer.layer_collection.children.new(collection_name)
            
            if layer.name.startswith('ch'):
                layer_collection.exclude = False
            elif layer.name.startswith('bg'):
                layer_collection.exclude = True
            else:
                layer_collection.exclude = True
                
class OBJECT_OT_update_shadow_material(bpy.types.Operator):
    bl_idname = "object.update_shadow_material"
    bl_label = "Update Shadow Material"
    
    def execute(self, context):
        shadow_material_name = "MI_shadow"

        shadow_mat = self.get_material(shadow_material_name)

        if not shadow_mat:
            self.report({'ERROR'}, "Could not find or load the material.")
            return {'CANCELLED'}

        # Replace the materials for all selected mesh objects
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                self.replace_matching_materials(obj, shadow_material_name, shadow_mat)
            else:
                print(f"Skipped {obj.name}: Not a mesh object.")
        
        return {'FINISHED'}

    def get_material(self, material_name):
        # Use the create_material method to get the material
        filepath = "M:/RND/SFtools/2025/lookdev/blend/ldvLight_v03.blend"
        if material_name not in bpy.data.materials:
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                if material_name in data_from.materials:
                    data_to.materials = [material_name]
                else:
                    print(f"Material {material_name} not found in {filepath}")
                    return None
        return bpy.data.materials.get(material_name)

    def replace_matching_materials(self, obj, material_prefix, new_material):
        for i, mat in enumerate(obj.data.materials):
            if mat and mat.name.startswith(material_prefix):
                print(f"Replacing material {mat.name} with {new_material.name} on object {obj.name}")
                obj.data.materials[i] = new_material


class OBJECT_OT_remove_shadow_catcher(bpy.types.Operator):
    bl_idname = "object.remove_shadow_catcher"
    bl_label = "Remove Shadow Catcher"

    def execute(self, context):
        obj = context.active_object
        if obj and obj.name.endswith("_shadow"):
            bpy.data.objects.remove(obj)
            # Remove object from collection if needed
        return {'FINISHED'}

################################################################
##################   CH_BLOCKER   ##############################
################################################################

class OBJECT_OT_apply_blocker(bpy.types.Operator):
    bl_idname = "object.apply_blocker"
    bl_label = "Apply Blocker"
    
    def execute(self, context):
        for obj in context.selected_objects:
            self.create_blocker(obj.name, "ch_blocker_col", "MI_ch_blocker")
        return {'FINISHED'}
    
    def create_blocker(self, obj_name, collection_name, material_name):
        obj = bpy.data.objects.get(obj_name)
        if not obj:
            print("Object not found.")
            return
        
        blocker_name = obj_name + "_blocker"
        if blocker_name in bpy.data.objects:
            print("Blocker object already exists.")
            return
        
        obj_copy = obj.copy()
        obj_copy.data = obj.data.copy()
        obj_copy.name = blocker_name
        
        # Create and assign the material
        mat = self.create_material(material_name)
        obj_copy.data.materials.clear()
        obj_copy.data.materials.append(mat)
        
        # Link the object to the existing collection
        collection = bpy.data.collections.get(collection_name)
        if collection and obj_copy.name not in collection.objects:
            collection.objects.link(obj_copy)

    def create_material(self, material_name):
        mat = bpy.data.materials.get(material_name)
        if not mat:
            mat = bpy.data.materials.new(name=material_name)
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            nodes.clear()

            trans_bsdf = nodes.new(type='ShaderNodeBsdfTransparent')
            material_output = nodes.new(type='ShaderNodeOutputMaterial')
            
            links.new(trans_bsdf.outputs['BSDF'], material_output.inputs['Surface'])
            
            mat.blend_method = 'BLEND'
            mat.shadow_method = 'NONE'
        
        return mat


class OBJECT_OT_remove_blocker(bpy.types.Operator):
    bl_idname = "object.remove_blocker"
    bl_label = "Remove Blocker"

    def execute(self, context):
        obj = context.active_object
        if obj and obj.name.endswith("_blocker"):
            bpy.data.objects.remove(obj)
            # Remove object from collection if needed
        return {'FINISHED'}
        
########################bake to shape key##################################        
        
def create_base_mesh(original_obj):
    # Duplicate the original object and convert to mesh with keep_original=True
    bpy.ops.object.select_all(action='DESELECT')
    original_obj.select_set(True)
    bpy.context.view_layer.objects.active = original_obj
    bpy.ops.object.convert(target='MESH', keep_original=True)
    base_obj = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = base_obj

    # Set base object name to the original object name with _cloth suffix
    base_obj.name = f"{original_obj.name}_baked"

    # Rename the original object with _orig suffix
    original_obj.name = f"{original_obj.name}_orig"
    
    return base_obj

def copy_modifiers(source_obj, target_obj, modifier_types):
    for modifier in source_obj.modifiers:
        if modifier.type in modifier_types:
            bpy.context.view_layer.objects.active = source_obj
            source_obj.select_set(True)
            target_obj.select_set(True)
            bpy.ops.object.modifier_copy_to_selected(modifier=modifier.name)
            target_obj.select_set(False)

def bake_shape_key_animation(base_obj, original_obj):
    # Ensure the base object has shape keys, create one if it does not
    if not base_obj.data.shape_keys:
        base_obj.shape_key_add(name="Basis")

    # Use the base object name as the shape key prefix
    shape_key_prefix = base_obj.data.name

    # Use current frame range
    frame_start = bpy.context.scene.frame_start
    frame_end = bpy.context.scene.frame_end

    # Create shape keys for each frame
    for frame in range(frame_start, frame_end + 1):
        bpy.context.scene.frame_set(frame)

        # Duplicate and convert the original object to mesh with keep_original=True
        bpy.ops.object.select_all(action='DESELECT')
        original_obj.select_set(True)
        bpy.context.view_layer.objects.active = original_obj
        bpy.ops.object.convert(target='MESH', keep_original=True)
        frame_obj = bpy.context.selected_objects[0]
        bpy.context.view_layer.objects.active = frame_obj

        # Ensure the number of vertices matches before creating the shape key
        if len(frame_obj.data.vertices) == len(base_obj.data.vertices):
            # Create a new shape key
            shape_key_name = f"{shape_key_prefix}_Frame_{frame}"
            new_shape_key = base_obj.shape_key_add(name=shape_key_name, from_mix=False)

            # Transfer the frame mesh shape to the new shape key
            base_mesh = base_obj.data
            frame_mesh = frame_obj.data
            for vert_base, vert_frame in zip(base_mesh.vertices, frame_mesh.vertices):
                new_shape_key.data[vert_base.index].co = vert_frame.co
            
            # Keyframe the shape key value to 1 at the current frame
            new_shape_key.value = 1.0
            new_shape_key.keyframe_insert(data_path="value", frame=frame)

            # Keyframe the shape key value to 0 at the previous and next frames
            if frame > frame_start:
                new_shape_key.value = 0.0
                new_shape_key.keyframe_insert(data_path="value", frame=frame-1)
            if frame < frame_end:
                new_shape_key.value = 0.0
                new_shape_key.keyframe_insert(data_path="value", frame=frame+1)
        else:
            print(f"Vertex count mismatch at frame {frame}: frame object has {len(frame_obj.data.vertices)} vertices, but base mesh has {len(base_obj.data.vertices)} vertices.")

        # Remove the frame object
        bpy.data.objects.remove(frame_obj, do_unlink=True)

    # Hide the original object in viewport and render
    original_obj.hide_viewport = True
    original_obj.hide_render = True

    # Copy solidify modifiers from the original object to the base object
    copy_modifiers(original_obj, base_obj, {'SOLIDIFY'})

    print(f"Shape key animation baked for {base_obj.name}.")

class BakeShapeKeysOperator(bpy.types.Operator):
    bl_idname = "object.bake_shape_keys"
    bl_label = "Bake Shape Keys"

    def execute(self, context):
        original_objects = context.selected_objects

        if original_objects:
            for original_obj in original_objects:
                if original_obj.type == 'MESH':
                    # Disable subdivision and solidify modifiers completely
                    original_modifiers = []
                    for modifier in original_obj.modifiers:
                        if modifier.type in {'SUBSURF', 'SOLIDIFY'}:
                            original_modifiers.append((modifier, modifier.show_viewport, modifier.show_render))
                            modifier.show_viewport = False
                            modifier.show_render = False

                    # Create base mesh
                    base_obj = create_base_mesh(original_obj)
                    
                    # Bake shape key animation
                    bake_shape_key_animation(base_obj, original_obj)

                    # Restore subdivision and solidify modifiers
                    for modifier, show_viewport, show_render in original_modifiers:
                        modifier.show_viewport = show_viewport
                        modifier.show_render = show_render
                else:
                    self.report({'WARNING'}, f"{original_obj.name} is not a mesh object.")
        else:
            self.report({'WARNING'}, "No objects selected.")
            return {'CANCELLED'}

        return {'FINISHED'}



class DeleteNonVisibleMeshesOperator(bpy.types.Operator):
    bl_idname = "object.delete_non_visible_meshes"
    bl_label = "Delete Non-Visible Meshes"
    bl_description = "Delete all non-visible mesh objects. Are you sure?"

    # UI 그리기 함수 (확인용 팝업)
    def draw(self, context):
        layout = self.layout
        layout.label(text="Delete all non-visible mesh objects?")  # 확인 메시지 표시

    # 팝업을 띄우는 함수
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)  # 확인용 팝업을 띄움

    # OK 버튼을 눌렀을 때 실행되는 함수
    def execute(self, context):
        # 보이는 메시 오브젝트의 이름을 모아두기
        visible_objects = {obj.name for obj in bpy.context.visible_objects if obj.type == 'MESH'}

        # 삭제할 오브젝트 목록을 먼저 생성 (이름을 저장)
        objects_to_delete = [obj.name for obj in bpy.data.objects if obj.type == 'MESH' and obj.name not in visible_objects]

        # 모든 오브젝트 삭제
        for obj_name in objects_to_delete:
            obj = bpy.data.objects.get(obj_name)  # 안전하게 오브젝트를 다시 참조
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
                self.report({'INFO'}, f"Deleted: {obj_name}")

        self.report({'INFO'}, "All non-visible mesh objects have been deleted.")
        return {'FINISHED'}


# 기존의 함수 정의
def replace_botaniq_library_path():
    keyword = "botaniq_lite"
    new_prefix = "m:\\e_utility\\blender\\add_on\\botaniq\\"

    # 라이브러리 파일 경로 변경
    for lib in bpy.data.libraries:
        if keyword in lib.filepath:
            # botaniq_lite 앞부분만 변경
            botaniq_index = lib.filepath.find(keyword)
            new_filepath = new_prefix + lib.filepath[botaniq_index:]
            print(f"Old Library Path: {lib.filepath}")
            print(f"New Library Path: {new_filepath}")
            lib.filepath = new_filepath

    print("Botaniq library path replacement complete.")

def replace_botaniq_texture_path():
    keyword = "botaniq_lite"
    new_prefix = "m:\\e_utility\\blender\\add_on\\botaniq\\"

    # 텍스처 파일 경로 변경
    for img in bpy.data.images:
        if img.filepath and keyword in img.filepath:
            # botaniq_lite 앞부분만 변경
            botaniq_index = img.filepath.find(keyword)
            new_filepath = new_prefix + img.filepath[botaniq_index:]
            print(f"Old Texture Path: {img.filepath}")
            print(f"New Texture Path: {new_filepath}")
            img.filepath = new_filepath

    print("Botaniq texture path replacement complete.")

# 오퍼레이터 정의
class ReplaceBotaniqLibraryPathOperator(bpy.types.Operator):
    bl_idname = "object.replace_botaniq_library_path"
    bl_label = "Replace Botaniq Library and Texture Paths"
    bl_description = "Replace botaniq_lite paths in the library and textures with a new path."

    # 버튼을 눌렀을 때 실행되는 함수
    def execute(self, context):
        replace_botaniq_library_path()
        replace_botaniq_texture_path()
        self.report({'INFO'}, "Botaniq library and texture paths have been replaced.")
        return {'FINISHED'}



def replace_sanctus_library_path():
    keyword = "Sanctus-Library"
    new_prefix = "m:\\e_utility\\blender\\add_on\\"

    # 라이브러리 경로 변경
    for lib in bpy.data.libraries:
        if keyword in lib.filepath:
            sanctus_index = lib.filepath.find(keyword)
            new_filepath = new_prefix + lib.filepath[sanctus_index:]
            print(f"Old Library Path: {lib.filepath}")
            print(f"New Library Path: {new_filepath}")
            lib.filepath = new_filepath
    
    # 이미지 경로 변경
    for image in bpy.data.images:
        if image.filepath and keyword in image.filepath:
            sanctus_index = image.filepath.find(keyword)
            new_filepath = new_prefix + image.filepath[sanctus_index:]
            print(f"Old Image Path: {image.filepath}")
            print(f"New Image Path: {new_filepath}")
            image.filepath = new_filepath
    
    # 메쉬에 포함된 외부 파일 경로 변경 (예: alembic이나 다른 외부 파일을 사용하는 경우)
    for mesh in bpy.data.meshes:
        if mesh.library and keyword in mesh.library.filepath:
            sanctus_index = mesh.library.filepath.find(keyword)
            new_filepath = new_prefix + mesh.library.filepath[sanctus_index:]
            print(f"Old Mesh Library Path: {mesh.library.filepath}")
            print(f"New Mesh Library Path: {new_filepath}")
            mesh.library.filepath = new_filepath

    print("Sanctus library path replacement complete.")

class ReplacesanctusLibraryPathOperator(bpy.types.Operator):
    bl_idname = "object.replace_sanctus_library_path"
    bl_label = "Replace Sanctus Library Path"
    bl_description = "Replace Sanctus-Library paths in the libraries, images, and meshes with a new path."

    def execute(self, context):
        replace_sanctus_library_path()
        self.report({'INFO'}, "Sanctus library paths have been replaced.")
        return {'FINISHED'}


class SetCyclesRenderSettings(bpy.types.Operator):
    bl_idname = "render.set_cycles_render_settings"
    bl_label = "Set Cycles Render Settings"
    
    def execute(self, context):
        # Render settings
        scene = bpy.context.scene
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'GPU'
        # scene.cycles.sample_clamp_indirect = 1
        scene.cycles.caustics_refractive = False
        scene.cycles.caustics_reflective = False
        scene.cycles.adaptive_threshold = 0.03
        scene.cycles.use_denoising = False
        scene.cycles.samples = 128
        
        # Add Denoising Data to view layers that are used for rendering
        for view_layer in scene.view_layers:
            if view_layer.use:  # Check if the view layer is set to be used for rendering
                view_layer.cycles.denoising_store_passes = True  # Enable Denoising Data pass
                view_layer.use_pass_vector = True

        self.report({'INFO'}, "Cycles settings applied and Denoising Data added to view layers.")
        return {'FINISHED'}

def menu_func(self, context):
    self.layout.operator(SetCyclesRenderSettings.bl_idname)

class DeleteAllFakeUsersOperator(bpy.types.Operator):
    bl_idname = "object.delete_all_fake_users"
    bl_label = "Delete All Fake Users"
    bl_description = "Delete all data blocks with Fake Users set."

    def execute(self, context):
        # 모든 페이크 유저가 설정된 데이터 블록을 삭제하는 함수
        data_blocks = [
            bpy.data.meshes, bpy.data.materials, bpy.data.textures,
            bpy.data.images, bpy.data.curves, bpy.data.lights
        ]
        
        for data in data_blocks:
            # 삭제할 블록을 미리 리스트로 저장
            blocks_to_delete = [block for block in data if block.use_fake_user]
            
            for block in blocks_to_delete:
                try:
                    # 데이터 블록이 삭제 가능한지 다시 확인
                    if block and block.use_fake_user:
                        data.remove(block)
                        print(f"{block.name} 페이크 유저 삭제 완료.")
                except ReferenceError:
                    # 이미 삭제된 블록에 대한 참조 오류 발생 시 건너뜀
                    pass
                except Exception as e:
                    print(f"{block.name} 삭제 실패: {e}")
        
        self.report({'INFO'}, "All fake user data blocks deleted.")
        return {'FINISHED'}

class NodeGroupLinkerOperator(bpy.types.Operator):
    bl_idname = "object.node_group_linker"
    bl_label = "Node Group Linker Operator"
    bl_description = "Link node group from an external library and update materials"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            node_group_linker = NodeGroupLinker("SF_paint", r"M:\e_utility\blender\shaders\sf_paint.blend")
            node_group_linker.link_node_group()
            node_group_linker.update_materials()
            
            self.report({'INFO'}, "Node group linked and materials updated successfully.")
        except Exception as e:
            self.report({'WARNING'}, f"An error occurred: {e}")
        return {'FINISHED'}

class NodeGroupLinker:
    def __init__(self, node_group_name, library_filepath):
        self.node_group_name = node_group_name.lower()  # 대소문자 구분 제거
        self.library_filepath = library_filepath
        self.linked_node_group = None

    def link_node_group(self):
        try:
            print(f"Attempting to load node group: {self.node_group_name} from {self.library_filepath}")
            with bpy.data.libraries.load(self.library_filepath, link=True) as (data_from, data_to):
                if self.node_group_name in [ng.lower() for ng in data_from.node_groups]:
                    data_to.node_groups = [self.node_group_name]
                    print(f"Node group '{self.node_group_name}' found and linked.")
                else:
                    print(f"Node group '{self.node_group_name}' not found in the library.")
                    raise Exception(f"Failed to load '{self.node_group_name}' from '{self.library_filepath}'.")
            
            # 링크된 노드 그룹 찾기
            for node_group in bpy.data.node_groups:
                if (node_group.library and 
                    node_group.library.filepath == self.library_filepath and 
                    node_group.name.lower() == self.node_group_name):
                    self.linked_node_group = node_group
                    print(f"Linked node group found: {self.linked_node_group}")
                    break
            
            if not self.linked_node_group:
                raise Exception(f"Failed to find linked node group '{self.node_group_name}' in the current scene.")

        except Exception as e:
            print(f"Error in linking node group: {e}")

    def update_materials(self):
        try:
            selected_objects = bpy.context.selected_objects
            updated_materials = 0
            for obj in selected_objects:
                if obj.type == 'MESH':  # 메쉬 오브젝트만 처리
                    for slot in obj.material_slots:
                        material = slot.material
                        if material and material.node_tree:
                            for node in material.node_tree.nodes:
                                if node.type == 'GROUP' and node.node_tree:
                                    # 대소문자 구분 없이 `SF_paint`가 포함된 노드 그룹을 찾고 교체
                                    if self.node_group_name in node.node_tree.name.lower():
                                        print(f"Found node: {node.name} with node tree: {node.node_tree.name}")
                                        node.node_tree = self.linked_node_group  # 노드 그룹 교체
                                        updated_materials += 1
                                        print(f"Updated material '{material.name}' with new node group.")
            
            # 결과 보고
            if updated_materials > 0:
                print(f"Updated {updated_materials} materials with '{self.node_group_name}' node group from '{self.library_filepath}'.")
            else:
                print(f"No materials found that use a node group containing '{self.node_group_name}' in the selected objects.")

        except Exception as e:
            print(f"Error in updating materials: {e}")




def set_scene_settings():
    """씬 및 Outliner 설정 변경"""
    # Outliner 설정
    for area in bpy.context.screen.areas:
        if area.type == 'OUTLINER':
            space = area.spaces.active
            space.show_restrict_column_viewport = True
            space.show_restrict_column_select = True
            space.show_restrict_column_holdout = True
            space.show_restrict_column_indirect_only = True

    # # Scene 단위 설정
    # scene = bpy.context.scene
    # if scene.unit_settings.length_unit != 'CENTIMETERS':
        # scene.unit_settings.length_unit = 'CENTIMETERS'

class OBJECT_OT_make_2com(bpy.types.Operator):
    bl_idname = "object.make_2com"
    bl_label = "Make 2com"
    bl_description = "Apply 2 comma animation with step modifier"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected.")
            return {'CANCELLED'}

        step_value = 2
        offset_value = 1

        for obj in selected_objects:
            has_cache = False
            has_shape_keys = False

            # 처리: Mesh Sequence Cache
            modifier = obj.modifiers.get("MeshSequenceCache")
            if modifier:
                cache_file = modifier.cache_file
                if cache_file:
                    # Override Frame 활성화
                    cache_file.override_frame = True

                    # 기존 키프레임 제거
                    if cache_file.animation_data and cache_file.animation_data.action:
                        action = cache_file.animation_data.action
                        for fcurve in action.fcurves:
                            # 기존 모디파이어 제거
                            for fmod in fcurve.modifiers:
                                fcurve.modifiers.remove(fmod)

                            action.fcurves.remove(fcurve)

                    # 새로운 키프레임 추가
                    scene = context.scene
                    start_frame = scene.frame_start
                    end_frame = scene.frame_end

                    cache_file.frame = start_frame
                    cache_file.keyframe_insert(data_path="frame", frame=start_frame)
                    cache_file.frame = end_frame
                    cache_file.keyframe_insert(data_path="frame", frame=end_frame)

                    # 키프레임을 리니어로 설정
                    if cache_file.animation_data and cache_file.animation_data.action:
                        for fcurve in cache_file.animation_data.action.fcurves:
                            for keyframe in fcurve.keyframe_points:
                                keyframe.interpolation = 'LINEAR'

                            # Step Modifier 추가
                            fmod = fcurve.modifiers.new(type='STEPPED')
                            fmod.frame_step = step_value
                            fmod.frame_offset = offset_value

                    has_cache = True

            # 처리: Shape Keys
            if obj.data and obj.data.shape_keys:
                shape_keys = obj.data.shape_keys.key_blocks
                for shape_key in shape_keys:
                    action = shape_key.id_data.animation_data.action if shape_key.id_data and shape_key.id_data.animation_data else None
                    if action:
                        for fcurve in action.fcurves:
                            # 기존 Step Modifier 제거
                            for fmod in fcurve.modifiers:
                                if fmod.type == 'STEPPED':
                                    fcurve.modifiers.remove(fmod)

                            # Step Modifier 추가
                            fmod = fcurve.modifiers.new(type='STEPPED')
                            fmod.frame_step = step_value
                            fmod.frame_offset = offset_value

                        has_shape_keys = True

            # 처리 결과 확인
            if not has_cache and not has_shape_keys:
                self.report({'WARNING'}, f"Object '{obj.name}' has no Mesh Sequence Cache or Shape Keys.")

        self.report({'INFO'}, "Make 2com applied successfully.")
        return {'FINISHED'}

# 오퍼레이터: Del 2com
class OBJECT_OT_del_2com(bpy.types.Operator):
    bl_idname = "object.del_2com"
    bl_label = "Del 2com"
    bl_description = "Remove 2 comma animation and modifiers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected.")
            return {'CANCELLED'}

        for obj in selected_objects:
            # 처리: Mesh Sequence Cache
            modifier = obj.modifiers.get("MeshSequenceCache")
            if modifier:
                cache_file = modifier.cache_file
                if cache_file:
                    # Override Frame 끄기
                    cache_file.override_frame = False

                    # F-Curve 및 키프레임 제거
                    if cache_file.animation_data and cache_file.animation_data.action:
                        action = cache_file.animation_data.action
                        for fcurve in list(action.fcurves):  # 안전한 삭제를 위해 리스트로 변환
                            action.fcurves.remove(fcurve)

            # 처리: Shape Key Modifiers
            if obj.data and obj.data.shape_keys:
                shape_keys = obj.data.shape_keys.key_blocks
                for shape_key in shape_keys:
                    action = shape_key.id_data.animation_data.action if shape_key.id_data and shape_key.id_data.animation_data else None
                    if action:
                        for fcurve in action.fcurves:
                            # Step Modifier 제거 (키프레임은 유지)
                            for fmod in fcurve.modifiers:
                                if fmod.type == 'STEPPED':
                                    fcurve.modifiers.remove(fmod)

        self.report({'INFO'}, "Del 2com applied successfully.")
        return {'FINISHED'}

class OBJECT_OT_instance_solidify(bpy.types.Operator):
    bl_idname = "object.instance_solidify"
    bl_label = "Instance Copy & Solidify"
    bl_description = "Create an instance copy, parent it to original, link material to object, rename it, and apply solidify"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects

        if not selected_objects:
            self.report({'WARNING'}, "No object selected")
            return {'CANCELLED'}

        for obj in selected_objects:
            # 선택한 오브젝트를 활성화
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.duplicate_move_linked(OBJECT_OT_duplicate={"linked": True})

            # 복제된 인스턴스 선택
            new_obj = context.object  # 방금 복제된 오브젝트

            # 새로운 이름 설정: 원본 오브젝트 이름 + "_shell"
            new_obj.name = obj.name + "_shell"

            # 복제된 오브젝트를 원본 오브젝트의 하위(페어런트)로 설정
            new_obj.parent = obj

            # 첫 번째 메터리얼 슬롯이 존재하면 Object로 링크 변경
            if new_obj.material_slots:
                new_obj.material_slots[0].link = 'OBJECT'

            # 솔리디파이 모디파이어 추가
            solidify = new_obj.modifiers.new(name="Solidify", type='SOLIDIFY')
            solidify.offset = 0.1
            solidify.thickness = 0.01
            
        return {'FINISHED'}

class OBJECT_OT_remove_shell(bpy.types.Operator):
    bl_idname = "object.remove_shell"
    bl_label = "Remove Shell Objects"
    bl_description = "Remove all child objects that end with _shell, including the selected object if it also ends with _shell"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects

        if not selected_objects:
            self.report({'WARNING'}, "No object selected")
            return {'CANCELLED'}

        for obj in selected_objects:
            # 만약 선택한 오브젝트 자체가 '_shell'로 끝난다면 삭제
            if obj.name.endswith("_shell"):
                bpy.data.objects.remove(obj, do_unlink=True)
                continue  # 이미 삭제된 경우 하위 오브젝트는 검사할 필요 없음

            # obj의 하위 오브젝트 중 '_shell'로 끝나는 오브젝트 삭제
            if obj.children:
                for child in obj.children[:]:  # 리스트 복사로 안전하게 삭제
                    if child.name.endswith("_shell"):
                        bpy.data.objects.remove(child, do_unlink=True)

        return {'FINISHED'}

def run_set_scene_from_file(dummy):
    bpy.ops.sf.set_scene_from_file()
    
def register_scene_loader_handler():
    if run_set_scene_from_file not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(run_set_scene_from_file)

    
class SF_OT_SetSceneFromFile(bpy.types.Operator):
    bl_idname = "sf.set_scene_from_file"
    bl_label = "Set Scene from File"

    def execute(self, context):
        import os, re, bpy
        scene = context.scene
        my_tool = scene.my_tool
        project_settings = scene.my_project_settings

        filepath = bpy.data.filepath
        if not filepath:
            self.report({'WARNING'}, "저장된 .blend 파일이 없습니다.")
            return {'CANCELLED'}

        filename = os.path.basename(filepath)

        # 예: DSC_0040_0060_ren_v003_line.blend
        #     └proj  └scn  └cut  └(중간토큰들) └버전 └접미사(옵션)
        m = re.match(
            r"([A-Za-z]+)_(\d{4})_(\d{4})(?:_[A-Za-z0-9]+)*_(v\d{3})(?:_([A-Za-z0-9]+))?\.blend",
            filename
        )
        if not m:
            self.report({'WARNING'}, f"파일명에서 정보를 추출할 수 없습니다: {filename}")
            return {'CANCELLED'}

        project, scene_number, cut_number, version, suffix = m.groups()
        project = project.upper()
        suffix = suffix or ""           # 예: "line" 또는 ""

        # 프로젝트 체크
        valid_projects = {'DSC', 'THE_TRAP', 'ARBOBION', 'FUZZ', 'BTS'}
        if project not in valid_projects:
            self.report({'WARNING'}, f"알 수 없는 프로젝트: {project}")
            return {'CANCELLED'}

        # 값 적용
        project_settings.projects = project
        my_tool.scene_number = scene_number
        my_tool.cut_number = cut_number

        # --- 핵심: blend_file Enum은 'v003'만 넣는다 (접미사는 버전이 아님)
        target_ver = version  # e.g. 'v003'

        # Enum 안전 세팅: enum에 'v003'이 없다면 'v003_*' 중 하나로 fallback
        try:
            my_tool.blend_file = target_ver
        except TypeError:
            # enum 목록 조회
            enum_prop = my_tool.bl_rna.properties['blend_file']
            enum_keys = [it.identifier for it in enum_prop.enum_items]
            # 정확히 일치하면 재시도
            if target_ver in enum_keys:
                my_tool.blend_file = target_ver
            else:
                # v003_* 중 가장 근접한 것 선택 (예: v003_line)
                candidates = [k for k in enum_keys if k.startswith(target_ver + "_")]
                if candidates:
                    my_tool.blend_file = candidates[0]
                else:
                    self.report({'WARNING'},
                        f"'{target_ver}' 버전을 enum에서 찾을 수 없습니다. 사용 가능: {enum_keys}")
                    # 그래도 나머지 정보는 셋업
                    self.report({'INFO'},
                        f"프로젝트:{project} 씬:{scene_number} 컷:{cut_number} (버전 세팅 생략)")
                    return {'FINISHED'}

        # (선택) 접미사를 어딘가에 저장하고 싶다면 여기서:
        #   - my_tool.output_suffix 같은 StringProperty가 있다면:
        # try:
        #     my_tool.output_suffix = suffix  # 'line' 등
        # except Exception:
        #     pass

        self.report({'INFO'},
            f"프로젝트:{project}, 씬:{scene_number}, 컷:{cut_number}, 버전:{target_ver}"
            + (f", 접미사:{suffix}" if suffix else "")
        )
        return {'FINISHED'}


def disable_line_nodes_in_materials(obj):
    """해당 메쉬의 모든 머티리얼에서 Line Intensity / Line Style 노드를 0으로 세팅"""
    for mat in obj.data.materials:
        if not (mat and mat.use_nodes and mat.node_tree):
            continue
        for node in mat.node_tree.nodes:
            # Float/Value 노드 타입만 체크
            if node.type == 'VALUE':
                if node.label in ["Line Intensity", "Line Style"]:
                    node.outputs[0].default_value = 0.0
                    print(f"[INFO] {obj.name}: {mat.name} → {node.label} 값 0으로 변경")


def convert_vgroup_to_color(obj, color_name="ToonkitLineID"):
    """버텍스 그룹 → 컬러 어트리뷰트 변환 (없어도 생성, 변환 실패 시 0으로 채움)"""
    if obj.type != 'MESH':
        return False

    mesh = obj.data

    # ToonkitLineID 없으면 새로 생성 (BYTE_COLOR, POINT)
    if color_name not in mesh.color_attributes:
        mesh.color_attributes.new(name=color_name, type='BYTE_COLOR', domain='POINT')

    color_layer = mesh.color_attributes[color_name]

    # === Case 1: 버텍스 그룹 없음 ===
    if not obj.vertex_groups:
        for i in range(len(color_layer.data)):
            color_layer.data[i].color = (0.0, 0.0, 0.0, 1.0)
        print(f"[INFO] {obj.name}: 버텍스 그룹 없음 → '{color_name}' 0으로 채움")
        return True

    # === Case 2: 활성 그룹 없음 ===
    vg = obj.vertex_groups.active
    if not vg:
        for i in range(len(color_layer.data)):
            color_layer.data[i].color = (0.0, 0.0, 0.0, 1.0)
        print(f"[INFO] {obj.name}: 활성 버텍스 그룹 없음 → '{color_name}' 0으로 채움")
        return True

    # === Case 3: 변환 성공 (Grayscale: R=G=B=weight) ===
    for i, v in enumerate(mesh.vertices):
        try:
            w = vg.weight(i)
        except RuntimeError:
            w = 0.0
        color_layer.data[i].color = (w, w, w, 1.0)

    print(f"[INFO] {obj.name}: 버텍스 그룹 '{vg.name}' → '{color_name}' 변환 완료 (Grayscale)")
    return True



def set_onlylines_for_special_mesh(obj):
    """메쉬 이름 조건에 따라 OnlyLines 값을 0/1로 설정"""
    keywords = ["eyebrow", "eyelash", "tongue", "toungue"]
    target = any(k in obj.name.lower() for k in keywords)  # 조건 맞으면 True → 1, 아니면 0

    changed = 0
    for mat in obj.data.materials:
        if not (mat and mat.use_nodes and mat.node_tree):
            continue

        for node in mat.node_tree.nodes:
            if node.type == 'GROUP':
                for inp in node.inputs:
                    if inp.name == "OnlyLines":
                        inp.default_value = int(1 if target else 0)
                        print(f"[INFO] {obj.name}: {mat.name} {node.name}.OnlyLines = {int(target)}")
                        changed += 1
    return changed > 0


# 고정할 옵션과 값 (여기만 수정하면 됨)
FIXED_LINE_OPTIONS = {
    "Core": 0,
    "Use Global": 0,
    "UseObj": 0,
    "Relative": 0,
    "UseSilluette": 1,
    "UseMatIdx": 0,
    "UseDepth": 0,
    "NormalLimit": 0.4,
    "Line Size": 0.085,
}

def force_fixed_line_options(obj):
    """모든 메터리얼에서 지정된 옵션들을 고정값으로 세팅"""
    changed = 0

    for mat in obj.data.materials:
        if not (mat and mat.use_nodes and mat.node_tree):
            continue

        for node in mat.node_tree.nodes:
            if node.type == 'GROUP':
                for inp in node.inputs:
                    if inp.name in FIXED_LINE_OPTIONS:
                        inp.default_value = FIXED_LINE_OPTIONS[inp.name]
                        print(f"[INFO] {obj.name}: {mat.name} {node.name}.{inp.name} → {FIXED_LINE_OPTIONS[inp.name]} 고정")
                        changed += 1
    return changed



def disable_special_mesh_object(obj):
    """특수 키워드 또는 네이밍 규칙(sn_geo)인 경우 오브젝트 숨김 처리"""
    if not obj or obj.type != 'MESH':
        return False

    name_l = obj.name.lower()
    keywords = ["eyebrow", "eyelash", "eye", "tongue", "toungue"]

    # 0) 네이밍 규칙: 'sn_'가 'geo' 앞에 붙은 형태 → 예: *_sn_geo
    if "sn_geo" in name_l:
        obj.hide_viewport = True
        obj.hide_render = True
        print(f"[INFO] {obj.name}: 'sn_geo' 네이밍 규칙 감지 → 숨김 처리됨")
        return True

    # 1) 이름 기반 키워드 체크
    if any(k in name_l for k in keywords):
        obj.hide_viewport = True
        obj.hide_render = True
        print(f"[INFO] {obj.name}: 키워드 기반 숨김 처리됨")
        return True

    return False


def normalize_version_to_line(filepath: str):
    """경로에서 v### 또는 v###_* 형태를 v###_line으로 교체"""
    import os, re
    parts = re.split(r'[\\/]', filepath)
    for i, p in enumerate(parts):
        m = re.match(r'^(v\d{3})', p, re.IGNORECASE)
        if m:
            base = m.group(1).lower()   # v001
            parts[i] = f"{base}_line"   # v001_line
            return os.path.normpath(os.sep.join(parts))
    return filepath

from bpy.props import EnumProperty

class SF_OT_UpdateToCyclesIndependent(bpy.types.Operator):
    bl_idname = "object.sf_update_to_cycles_independent"
    bl_label = "Make Outline Scene"
    bl_description = "EEVEE 세팅 + chOutline 생성 + ViewLayer 선택 옵션"
    bl_options = {'REGISTER'}

    layer_choice: EnumProperty(
        name="Target ViewLayer",
        description="Choose which ViewLayer to activate",
        items=[
            ('SELECTED', "Selected Layer", "Keep current active ViewLayer"),
            ('CH', "ch_vl auto select", "Switch to ch_vl, or fallback to first containing 'ch'")
        ],
        default='CH'
    )

    def invoke(self, context, event):
        # 이걸 쓰면 드롭다운이 아니라 라디오 버튼으로 나옴
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Which ViewLayer to use?")
        layout.prop(self, "layer_choice", expand=True)  # 👈 expand=True → 라디오 버튼 표시

    def execute(self, context):
        scene = context.scene

        if self.layer_choice == 'CH':
            target_vl = None
            for vl in scene.view_layers:
                if vl.name == "ch_vl":
                    target_vl = vl
                    break
            if not target_vl:
                for vl in scene.view_layers:
                    if "ch" in vl.name.lower():
                        target_vl = vl
                        break
            if target_vl:
                bpy.context.window.view_layer = target_vl
                self.report({'INFO'}, f"ViewLayer 활성화: {target_vl.name}")
            else:
                self.report({'WARNING'}, "조건에 맞는 뷰레이어 없음, 기존 상태 유지")
        else:
            self.report({'INFO'}, "현재 선택된 ViewLayer 유지")
            
        sc = context.scene
        scene = context.scene


        # --- A. ViewLayer 이름 보정 ---
        active_vl = bpy.context.window.view_layer
        if not any(vl.name.startswith("line") for vl in scene.view_layers):
            old = active_vl.name
            active_vl.name = "line_vl"
            print(f"[INFO] ViewLayer '{old}' → 'line_vl'")
        else:
            print("[INFO] 'line*' ViewLayer 존재 → 이름 변경 생략")
            
            
        # --- B. Current 버튼 실행 ---
        try:
            bpy.ops.sf.version_operator(increment=-999)
            print("[INFO] Current 버튼 실행 완료")
        except Exception as e:
            self.report({'WARNING'}, f"Current 버튼 실행 실패: {e}")

        # --- B2. Output Path 'line' 버튼 실행 ---
        try:
            bpy.ops.sf.set_output_path(prefix="line")
            print("[INFO] Output Path 'line' 버튼 실행 완료")
        except Exception as e:
            self.report({'WARNING'}, f"Output Path 'line' 버튼 실행 실패: {e}")


        # --- C. EEVEE 세팅 ---
        available_engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
        if 'BLENDER_EEVEE_NEXT' in available_engines:
            sc.render.engine = 'BLENDER_EEVEE_NEXT'
        else:
            sc.render.engine = 'BLENDER_EEVEE'
        print(f"[INFO] EEVEE 세팅 완료: {sc.render.engine}")

        # --- D. chOutline_col + chOutline 생성 ---
        outline_col_name = "chOutline_col"
        outline_obj_name = "chOutline"

        root_col = context.scene.collection
        outline_col = bpy.data.collections.get(outline_col_name)
        if not outline_col:
            outline_col = bpy.data.collections.new(outline_col_name)
            root_col.children.link(outline_col)

        if not bpy.data.objects.get(outline_obj_name):
            prev_layer_collection = context.view_layer.active_layer_collection

            # 레이어콜렉션 찾기
            def find_layer_collection(layer_collection, target_name):
                if layer_collection.collection.name == target_name:
                    return layer_collection
                for child in layer_collection.children:
                    found = find_layer_collection(child, target_name)
                    if found:
                        return found
                return None

            out_layer = find_layer_collection(context.view_layer.layer_collection, outline_col_name)
            if out_layer:
                context.view_layer.active_layer_collection = out_layer

            # 라인아트 GP 생성 (컬렉션 기반)
            bpy.ops.object.gpencil_add(
                align='WORLD',
                location=(0, 0, 0),
                scale=(1, 1, 1),
                type='LRT_COLLECTION'
            )
            gp_obj = bpy.context.object
            gp_obj.name = outline_obj_name

            # 반드시 chOutline_col 안에 배치
            if gp_obj.name not in outline_col.objects:
                outline_col.objects.link(gp_obj)
                context.scene.collection.objects.unlink(gp_obj)

            # outlineDel 버텍스 그룹 추가
            if "outlineDel" not in gp_obj.vertex_groups.keys():
                gp_obj.vertex_groups.new(name="outlineDel")

            # Line Art 모디파이어 세팅
            mod = gp_obj.grease_pencil_modifiers.get("Line Art")
            if mod:
                mod.source_type = 'COLLECTION'
                
                ch_col = bpy.data.collections.get("ch_col")
                if ch_col:
                    mod.source_collection = ch_col
                    print(f"[INFO] Line Art 소스 → {ch_col.name}")
                else:
                    print("[WARN] ch_col 컬렉션을 찾지 못했습니다.")
                
                # mod.source_collection = context.scene.collection
                mod.target_layer = "Lines"
                mod.thickness = 1
                mod.opacity = 1
                mod.use_contour = True
                mod.silhouette_filtering = 'NONE'
                mod.use_intersection = False
                mod.use_crease = True
                mod.use_material = False
                mod.use_edge_mark = True
                mod.use_loose = True
                mod.use_light_contour = False
                mod.use_shadow = False
                mod.use_overlap_edge_type_support = True
                mod.source_vertex_group = "outlineDel"
                mod.use_output_vertex_group_match_by_name = True

            # Opacity 모디파이어 추가
            bpy.context.view_layer.objects.active = gp_obj
            bpy.ops.object.gpencil_modifier_add(type='GP_OPACITY')
            op_mod = gp_obj.grease_pencil_modifiers.get("Opacity")
            if op_mod:
                op_mod.use_weight_factor = True
                op_mod.modify_color = 'STROKE'
                op_mod.vertex_group = "outlineDel"
                op_mod.invert_vertex = True

            # GP 데이터 세팅
            gp_obj.data.stroke_thickness_space = 'SCREENSPACE'
            gp_obj.data.pixel_factor = 2

            # 원래 활성 콜렉션 복원
            context.view_layer.active_layer_collection = prev_layer_collection

        print("[INFO] Outline Scene 생성 완료")

        # --- D2. Outline Grease Pencil Material Base Color 화이트로 변경 ---
        gp_obj = bpy.data.objects.get("chOutline")
        if gp_obj and gp_obj.type == 'GPENCIL':
            if gp_obj.data.materials:
                for mat in gp_obj.data.materials:
                    if mat and mat.grease_pencil:  # GPencil 전용 재질
                        style = mat.grease_pencil
                        style.color = (1.0, 1.0, 1.0, 1.0)  # Stroke/Base Color → White
                        print(f"[INFO] Grease Pencil Material '{mat.name}' Base Color → White")
            else:
                print("[WARN] chOutline 오브젝트에 머티리얼이 없음")
        else:
            print("[WARN] chOutline GP 오브젝트를 찾을 수 없음")

        # --- E. 특정 매쉬들 하이드 처리 ---
        hide_keywords = ["eye", "tooth", "teeth", "tongue", "toungue", "cornea"]
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                name_lower = obj.name.lower()
                if any(k in name_lower for k in hide_keywords):
                    obj.hide_viewport = True
                    obj.hide_render = True
                    print(f"[INFO] 숨김 처리: {obj.name}")
        # --- F. MeshSequenceCache 모디파이어 세팅 ---
        updated_cache_count = 0
        for obj in bpy.data.objects:
            if obj.type != 'MESH':
                continue
            msc = obj.modifiers.get("MeshSequenceCache")
            if msc:
                msc.read_data = {'VERT', 'UV', 'COLOR'}
                updated_cache_count += 1
        # print(f"[INFO] MeshSequenceCache 업데이트: {updated_cache_count}개")

        # --- F0. 출력 포맷 강제 변경 ---
        set_output_png(sc.render.image_settings, alpha=False, label="Outline Output: ")
        print("[INFO] 출력 포맷: PNG (RGB)")

        # --- F. 출력 경로 처리 ---
        try:
            sc.render.filepath = normalize_version_to_line(sc.render.filepath)
            my_tool = scene.my_tool if hasattr(scene, "my_tool") else None
            if my_tool:
                scene_number = my_tool.scene_number
                cut_number = my_tool.cut_number
                dirpath = os.path.dirname(sc.render.filepath)
                new_filename = f"{scene_number}_{cut_number}_line_"
                sc.render.filepath = os.path.join(dirpath, new_filename)
            print(f"[INFO] 출력 경로 갱신: {sc.render.filepath}")
        except Exception as e:
            print(f"[WARN] 출력 경로 정규화 중 오류: {e}")
            
        # --- G. ViewLayer 렌더 활성화 제어 ---
        for vl in scene.view_layers:
            if "line" in vl.name.lower():
                vl.use = True
                print(f"[INFO] ViewLayer '{vl.name}' → Render ON")
            else:
                vl.use = False
                print(f"[INFO] ViewLayer '{vl.name}' → Render OFF")

        return {'FINISHED'}

import bpy

class SF_OT_BakeOutline(bpy.types.Operator):
    """chOutline 라인아트를 Bake하고, 뷰포트 표시 및 출력 설정을 정리합니다"""
    bl_idname = "object.sf_bake_outline"
    bl_label = "Bake Outline"
    bl_description = "chOutline 라인아트 Bake 후 ViewLayer에서 ch_col 컬렉션 비활성화 및 출력 포맷 변경"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        # 실행 전에 확인 팝업
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        sc = context.scene
        outline_obj_name = "chOutline"
        outline_obj = bpy.data.objects.get(outline_obj_name)

        # --- 대상 오브젝트 확인 ---
        if not outline_obj or outline_obj.type != 'GPENCIL':
            self.report({'ERROR'}, f"Grease Pencil 오브젝트 '{outline_obj_name}'을(를) 찾을 수 없습니다.")
            return {'CANCELLED'}

        # --- Line Art → Stroke Bake ---
        try:
            bpy.context.view_layer.objects.active = outline_obj
            bpy.ops.object.lineart_bake_strokes()
            self.report({'INFO'}, f"{outline_obj_name} 베이크 완료")
        except Exception as e:
            self.report({'ERROR'}, f"Line Art Bake 실패: {e}")
            return {'CANCELLED'}

        # --- 출력 포맷 PNG + RGB ---
        set_output_png(sc.render.image_settings, alpha=False, label="Outline Output: ")
        print("[INFO] 출력 포맷: PNG (RGB)")

        # --- ViewLayer에서 ch_col 컬렉션 비활성화 ---
        def find_layer_collection(layer_collection, target_name):
            if layer_collection.collection.name == target_name:
                return layer_collection
            for child in layer_collection.children:
                found = find_layer_collection(child, target_name)
                if found:
                    return found
            return None

        layer_col = find_layer_collection(context.view_layer.layer_collection, "ch_col")
        if layer_col:
            layer_col.exclude = True
            print("[INFO] ViewLayer에서 'ch_col' 컬렉션 비활성화 완료")
        else:
            self.report({'WARNING'}, "현재 ViewLayer에서 'ch_col' 컬렉션을 찾지 못했습니다.")

        return {'FINISHED'}

class SF_OT_ClearBakeOutline(bpy.types.Operator):
    """Bake된 라인아트를 지우고 원래 Line Art 모디파이어 상태로 되돌립니다"""
    bl_idname = "object.sf_clear_bake_outline"
    bl_label = "Clear Bake Outline"
    bl_description = "chOutline 오브젝트의 베이크된 Stroke를 제거하고 'ch_col' 컬렉션을 다시 활성화합니다."
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        # 실행 전에 확인 팝업
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        outline_obj_name = "chOutline"
        outline_obj = bpy.data.objects.get(outline_obj_name)

        # --- 대상 오브젝트 확인 ---
        if not outline_obj or outline_obj.type != 'GPENCIL':
            self.report({'ERROR'}, f"Grease Pencil 오브젝트 '{outline_obj_name}'을(를) 찾을 수 없습니다.")
            return {'CANCELLED'}

        # --- Clear Bake 실행 ---
        try:
            bpy.context.view_layer.objects.active = outline_obj
            bpy.ops.object.lineart_clear()
            self.report({'INFO'}, f"{outline_obj_name} Clear Bake 완료")
        except Exception as e:
            self.report({'ERROR'}, f"Clear Bake 실패: {e}")
            return {'CANCELLED'}

        # --- ViewLayer에서 ch_col 컬렉션 다시 켜기 ---
        def find_layer_collection(layer_collection, target_name):
            if layer_collection.collection.name == target_name:
                return layer_collection
            for child in layer_collection.children:
                found = find_layer_collection(child, target_name)
                if found:
                    return found
            return None

        layer_col = find_layer_collection(context.view_layer.layer_collection, "ch_col")
        if layer_col:
            layer_col.exclude = False
            print("[INFO] ViewLayer에서 'ch_col' 컬렉션 다시 활성화 완료")
        else:
            self.report({'WARNING'}, "현재 ViewLayer에서 'ch_col' 컬렉션을 찾지 못했습니다.")

        return {'FINISHED'}

class SF_OT_UpdateFromPublish(bpy.types.Operator):
    bl_idname = "sf.update_from_publish"
    bl_label = "Update From Publish (Smart)"
    bl_description = "기존 어셋을 삭제하고 최신 소스 파일(mod)로 교체(Re-Import)합니다"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        updated_count = 0
        
        # 1. 전역 설정에서 경로 및 접두사 로드 (BTS 지원)
        base_drive = get_project_paths() # "B:\", "S:\" 등
        prefix = get_project_prefix()    # "BTS", "DSC" 등
        
        if not base_drive:
            self.report({'ERROR'}, "프로젝트 경로를 찾을 수 없습니다.")
            return {'CANCELLED'}

        selected_items = []
        for category in scene.sf_file_categories:
            for item in category.items:
                if item.is_selected:
                    selected_items.append((category.name, item.name))

        if not selected_items:
            self.report({'WARNING'}, "선택된 어셋이 없습니다.")
            return {'CANCELLED'}

        # 2. 각 어셋에 대해 '삭제 후 재임포트' 수행
        for cat_name, asset_name in selected_items:
            print(f"--- [Reset to Pub] {asset_name} ({cat_name}) ---")
            
            # (1) 기존 어셋 삭제 (Collection & Objects)
            self.delete_asset_collections(asset_name)
            
            # (2) 퍼블리시(Source Mod) 파일 경로 구성
            folder_map = cat_name # 'ch', 'bg', 'prop'
            
            blend_path = os.path.join(base_drive, "assets", folder_map, asset_name, "mod", f"{asset_name}.blend")
            
            if not os.path.exists(blend_path):
                print(f"[Error] 파일을 찾을 수 없음: {blend_path}")
                self.report({'WARNING'}, f"파일 없음: {blend_path}")
                continue

            # (3) USD 캐시 경로 구성 (임포트 후 자동 연결용)
            sn = scene.my_tool.scene_number
            cn = scene.my_tool.cut_number
            cache_dir = os.path.join(base_drive, "scenes", sn, cn, "ren", "cache").replace("\\", "/")
            
            usd_file_name = f"{prefix}_{sn}_{cn}_{cat_name}_{asset_name}.usd"
            usd_path = os.path.join(cache_dir, usd_file_name).replace("\\", "/")
            
            # 와일드카드 검색 시 정확한 카테고리와 어셋명 매칭 규칙 적용
            search_target = f"_{cat_name}_{asset_name}.".lower()
            if not os.path.exists(usd_path) and os.path.exists(cache_dir):
                for f in os.listdir(cache_dir):
                    if f.lower().endswith(".usd") and search_target in f.lower():
                        usd_path = os.path.join(cache_dir, f).replace("\\", "/")
                        usd_file_name = f
                        break

            # (4) 재임포트 실행
            try:
                self.reimport_asset(blend_path, cat_name, asset_name, context, usd_path, usd_file_name)
                updated_count += 1
            except Exception as e:
                print(f"[Error] {asset_name} 업데이트 실패: {e}")

        self.report({'INFO'}, f"총 {updated_count}개 어셋 최신화 완료 (Delete & Re-Import)")
        return {'FINISHED'}

    def delete_asset_collections(self, asset_name):
        """기존 컬렉션을 삭제"""
        for suffix in ["_col", "_light_col"]:
            col = bpy.data.collections.get(asset_name + suffix)
            if col:
                for obj in col.objects:
                    bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.collections.remove(col)

    def reimport_asset(self, blend_path, cat_name, asset_name, context, usd_path, usd_file_name):
        """Source Blend에서 컬렉션을 가져오고 USD를 연결"""
        target_col_name = f"{asset_name}_col"
        light_col_name = f"{asset_name}_light_col"
        
        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            cols = [c for c in data_from.collections if c in [target_col_name, light_col_name]]
            data_to.collections = cols
            
        parent_col_name = f"{cat_name}_col"
        p_col = bpy.data.collections.get(parent_col_name)
        if not p_col:
            p_col = bpy.data.collections.new(parent_col_name)
            context.scene.collection.children.link(p_col)
            
        for col in data_to.collections:
            if col:
                p_col.children.link(col)
                if usd_path and os.path.exists(usd_path):
                    self.apply_cache(col, asset_name, usd_path, usd_file_name)

    def apply_cache(self, collection, asset_name, usd_path, usd_file_name):
        for obj in collection.all_objects:
            if obj.type == 'MESH':
                # 엠티 하위인지 확인 (오타 수정된 안전장치)
                is_real_mesh = False
                curr = obj.parent
                while curr:
                    name_parts = curr.name.split('.')
                    base_name = name_parts
                    if base_name == asset_name:
                        is_real_mesh = True
                        break
                    curr = curr.parent

                if is_real_mesh:
                    # 🔥 [완벽 복구] 원래 모디파이어가 있는 애들만 찾아서 갱신! (새로 만들지 않음)
                    for mod in obj.modifiers:
                        if mod.type == 'MESH_SEQUENCE_CACHE':
                            unique_name = f"{usd_file_name}_{obj.name}"
                            cf = bpy.data.cache_files.get(unique_name) or bpy.data.cache_files.load(usd_path)
                            cf.name = unique_name
                            cf.filepath = usd_path
                            mod.cache_file = cf
                            
                            # 프림 패스 보정
                            if mod.object_path and '/' in mod.object_path:
                                parts = mod.object_path.split('/')
                                if len(parts) > 1:
                                    parts = asset_name
                                    mod.object_path = '/'.join(parts)
                                    
class SF_OT_SetOutputPath(bpy.types.Operator):
    bl_idname = "sf.set_output_path"
    bl_label = "Set Output Path"

    prefix: bpy.props.StringProperty(name="Prefix", default="")  # 사용자 입력 프리픽스

    def execute(self, context):
        import os, re
        sc = context.scene

        # 🔹 블렌드 파일 이름에서 씬 / 컷 번호 추출
        blend_name = os.path.basename(bpy.data.filepath)
        match = re.search(r"(\d{4})_(\d{4})", blend_name)
        if not match:
            self.report({'WARNING'}, f"Cannot find scene/cut in filename: {blend_name}")
            return {'CANCELLED'}

        scene_number, cut_number = match.groups()

        # 기존 렌더 경로
        filepath = sc.render.filepath
        if not filepath:
            self.report({'WARNING'}, "Output path is empty")
            return {'CANCELLED'}

        dirpath = os.path.dirname(filepath)

        # 버전 추출 (예: v001)
        match = re.search(r"(v\d{3})", dirpath)
        if not match:
            self.report({'WARNING'}, "Version not found in path")
            return {'CANCELLED'}

        version = match.group(1)
        new_version = f"{version}_{self.prefix}" if self.prefix else version

        # 경로 재구성
        new_filename = f"{scene_number}_{cut_number}_{self.prefix}_" if self.prefix else f"{scene_number}_{cut_number}_"
        new_dirpath = re.sub(r"(v\d{3}.*)$", new_version, dirpath)

        new_path = os.path.join(new_dirpath, new_filename)
        sc.render.filepath = new_path

        # 🔹 line 전용 PNG 강제 세팅
        if self.prefix == "line":
            set_output_png(sc.render.image_settings, alpha=False, label="Output Path line: ")
        else:
            set_output_exr_multilayer(sc.render.image_settings, label="Output Path EXR: ")

        self.report({'INFO'}, f"Output path set from filename: {new_path}")
        return {'FINISHED'}



class SF_OT_SaveIncrementalSuffix(bpy.types.Operator):
    bl_idname = "sf.save_incremental_suffix"
    bl_label = "Incremental Save"

    suffix_items = [
        ('default', "Default", "No suffix (just v002)"),
        ('ch', "ch", "Character"),
        ('bg', "bg", "Background"),
        ('prop', "prop", "Prop"),
        ('mask', "mask", "Mask"),
        ('line', "line", "Line"),
    ]
    suffix: bpy.props.EnumProperty(
        name="Suffix",
        description="Choose suffix for new version",
        items=suffix_items,
        default='default'
    )

    custom_suffix: bpy.props.StringProperty(
        name="Custom",
        description="Custom suffix (if not empty, overrides above)",
        default=""
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout

        # 1줄: Default / ch / bg
        row = layout.row(align=True)
        row.prop_enum(self, "suffix", 'default')
        row.prop_enum(self, "suffix", 'ch')
        row.prop_enum(self, "suffix", 'bg')

        # 2줄: prop / mask / line
        row = layout.row(align=True)
        row.prop_enum(self, "suffix", 'prop')
        row.prop_enum(self, "suffix", 'mask')
        row.prop_enum(self, "suffix", 'line')

        # 3줄: 항상 표시되는 Custom 입력칸
        row = layout.row(align=True)
        row.label(text="Custom:")
        row.prop(self, "custom_suffix", text="")

    def execute(self, context):
        filepath = bpy.data.filepath
        if not filepath:
            self.report({'WARNING'}, "현재 파일이 저장되지 않았습니다.")
            return {'CANCELLED'}

        dirpath = os.path.dirname(filepath)
        filename = os.path.basename(filepath)

        # 버전 찾기
        match = re.search(r"(v\d{3})", filename)
        if not match:
            self.report({'WARNING'}, "파일명에서 버전을 찾을 수 없습니다.")
            return {'CANCELLED'}

        version_str = match.group(1)  # "v001"
        version_num = int(version_str[1:])
        new_version_str = f"v{version_num+1:03d}"

        # suffix 결정
        if self.custom_suffix.strip():
            suffix_str = self.custom_suffix.strip()
        elif self.suffix == 'default':
            suffix_str = ""
        else:
            suffix_str = self.suffix

        new_version_full = f"{new_version_str}_{suffix_str}" if suffix_str else new_version_str

        # 새 파일명
        new_filename = re.sub(r"v\d{3}.*\.blend$", new_version_full + ".blend", filename)
        new_filepath = os.path.join(dirpath, new_filename)

        bpy.ops.wm.save_as_mainfile(filepath=new_filepath, copy=False)

        self.report({'INFO'}, f"Saved as {new_filename}")
        return {'FINISHED'}

library_path = os.path.normpath(r"M:\RND\SFtools\2025\lookdev\blend\SF_Paint.blend")
target_group_name = "SF_Paint"

# --------------------------------------------------------
# 기능 1: SF_Paint 노드그룹 링크 + 교체
# --------------------------------------------------------
def ensure_linked_group():
    for ng in bpy.data.node_groups:
        if ng.library and ng.name == target_group_name:
            libpath = os.path.normpath(bpy.path.abspath(ng.library.filepath))
            if libpath == library_path:
                return ng

    directory = library_path + "\\NodeTree\\"
    filepath = directory + target_group_name

    bpy.ops.wm.link(
        filepath=filepath,
        directory=directory,
        filename=target_group_name,
        link=True
    )

    for ng in bpy.data.node_groups:
        if ng.library and ng.name.startswith(target_group_name):
            libpath = os.path.normpath(bpy.path.abspath(ng.library.filepath))
            if libpath == library_path:
                return ng
    return None

def relink_sf_paint_nodes():
    linked_group = ensure_linked_group()
    if not linked_group:
        return 0

    replaced_count = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "GROUP" and node.node_tree:
                if node.node_tree.name.lower().startswith("sf_paint"):
                    node.node_tree = linked_group
                    replaced_count += 1
    return replaced_count

# --------------------------------------------------------
# 기능 2: Alpha Hashed → Opaque 변환
# --------------------------------------------------------
def set_alpha_hashed_to_opaque():
    count = 0
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        if hasattr(mat, "blend_method") and mat.blend_method == 'HASHED':
            mat.blend_method = 'OPAQUE'
            count += 1
    return count

# --------------------------------------------------------
# 통합 실행 오퍼레이터
# --------------------------------------------------------
class SF_OT_AllInOne(bpy.types.Operator):
    """SF_Paint 교체 + Alpha Hashed → Opaque 변환"""
    bl_idname = "sf.all_in_one"
    bl_label = "Fix Paint + Opaque"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        paint_count = relink_sf_paint_nodes()
        opaque_count = set_alpha_hashed_to_opaque()
        self.report({'INFO'}, f"SF_Paint {paint_count}개 교체, 머티리얼 {opaque_count}개 변경")
        return {'FINISHED'}

def get_render_preset_json_path(project_name=None):
    """
    현재 프로젝트 기준 renderPreset.json 경로 반환
    예:
        THE_TRAP -> T:/_json/renderPreset.json
        DSC      -> S:/_json/renderPreset.json
        FUZZ     -> Z:/_json/renderPreset.json
    """
    base_path = get_project_paths(project_name)
    if not base_path:
        return None
    return os.path.join(base_path, "_json", "renderPreset.json")


def load_render_presets(project_name=None):
    """
    현재 프로젝트의 _json/renderPreset.json 을 읽어 프리셋 딕셔너리 반환
    """
    json_path = get_render_preset_json_path(project_name)

    if not json_path:
        print("[RenderPreset] 프로젝트 경로를 찾을 수 없습니다.")
        return {}

    if not os.path.exists(json_path):
        print(f"[RenderPreset] renderPreset.json 없음: {json_path}")
        return {}

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, dict):
            print(f"[RenderPreset] JSON 최상위 구조가 dict가 아닙니다: {json_path}")
            return {}

        print(f"[RenderPreset] 로드 완료: {json_path}")
        return data

    except Exception as e:
        print(f"[RenderPreset] JSON 불러오기 실패: {json_path} / {e}")
        return {}


def get_preset_items(self, context):
    """
    현재 프로젝트 기준 프리셋 목록을 EnumProperty 아이템으로 반환
    """
    presets = load_render_presets()
    items = [(key, key, f"Apply {key} render preset") for key in presets.keys()]
    return items if items else [("NONE", "None", "No presets found")]


class SF_OT_ApplyRenderPresets(bpy.types.Operator):
    """선택한 Render Preset 적용"""
    bl_idname = "sf.apply_render_presets"
    bl_label = "Apply Render Presets"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        presets = load_render_presets()
        preset_name = scene.render_preset_enum

        if preset_name == "NONE":
            self.report({'ERROR'}, "적용할 Render Preset이 없습니다.")
            return {'CANCELLED'}

        if preset_name not in presets:
            self.report({'ERROR'}, f"{preset_name} 프리셋을 찾을 수 없습니다.")
            return {'CANCELLED'}

        preset = presets[preset_name]
        self.apply_preset(context, preset_name, preset)
        self.report({'INFO'}, f"{preset_name} 프리셋 적용 완료")
        return {'FINISHED'}

    def apply_preset(self, context, preset_name, preset):
        scene = context.scene
        render_settings = preset.get("render_settings", {})

        # --- 일반 render_settings 적용 ---
        for key, value in render_settings.items():
            try:
                set_nested_property(scene, key, value)
            except Exception as e:
                print(f"[WARN] {key} 적용 실패: {e}")



class SF_OT_SetLightBounces(bpy.types.Operator):
    """씬의 모든 라이트의 max_bounces 값을 1024로 설정"""
    bl_idname = "sf.set_light_bounces"
    bl_label = "Set Light Bounces to 1024"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        count = 0
        for obj in bpy.data.objects:
            if obj.type == 'LIGHT':
                try:
                    obj.data.cycles.max_bounces = 1024
                    count += 1
                except AttributeError:
                    # 라이트 타입에 따라 cycles 속성이 없을 수도 있음
                    self.report({'WARNING'}, f"{obj.name}에는 cycles.max_bounces 속성이 없음")
        self.report({'INFO'}, f"{count}개의 라이트를 1024로 설정 완료")
        return {'FINISHED'}

# =========================
# Make Color Pass Operator
# =========================
import bpy
from bpy.props import EnumProperty

class SF_OT_MakeColorPass(bpy.types.Operator):
    bl_idname = "sf.make_color_pass"
    bl_label  = "Make Color Pass"
    bl_options = {'REGISTER', 'UNDO'}

    layer_choice: EnumProperty(
        name="Target ViewLayer",
        items=[
            ('SELECTED', "Selected Layer", "현재 활성 레이어 유지"),
            ('RENAME',   "Rename ch_vl → chCol_vl", "ch_vl의 이름만 chCol_vl로 변경"),
        ],
        default='RENAME',
    )

    # --- 헬퍼: RGBA 커스텀 프로퍼티 강제 (Linear Float Array + UI COLOR) ---
    def _ensure_color_idprop_rgba(self, id_block, key, rgba=(1.0,1.0,1.0,1.0)):
        try:
            need_reset = True
            if hasattr(id_block, "keys") and (key in id_block.keys()):
                v = id_block[key]
                if isinstance(v, (list, tuple)) and len(v) in (3, 4):
                    need_reset = False

            if need_reset:
                try:
                    if key in id_block.keys():
                        del id_block[key]
                except Exception:
                    pass
                id_block[key] = (float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3]))
            else:
                if len(id_block[key]) == 3:
                    id_block[key] = (float(rgba[0]), float(rgba[1]), float(rgba[2]))
                else:
                    id_block[key] = (float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3]))

            try:
                ui = id_block.id_properties_ui(key)
                ui.update(subtype='COLOR', min=0.0, max=1.0, soft_min=0.0, soft_max=1.0, default=id_block[key])
            except Exception:
                pass
        except Exception as e:
            print(f"[WARN] _ensure_color_idprop_rgba failed on {getattr(id_block,'name',type(id_block))}.{key}: {e}")

    # --- 헬퍼: 모든 머티리얼 'Shadow Color' 입력 화이트 ---
    def _set_all_shadow_color_inputs_white(self):
        WHITE4 = (1.0, 1.0, 1.0, 1.0)
        cnt = 0
        for mat in bpy.data.materials:
            if not (mat and mat.use_nodes and mat.node_tree):
                continue
            for node in mat.node_tree.nodes:
                for inp in getattr(node, "inputs", []):
                    if inp.name == "Shadow Color" and hasattr(inp, "default_value"):
                        try:
                            inp.default_value = WHITE4
                            cnt += 1
                        except Exception as e:
                            print(f"[WARN] Shadow Color set failed on {mat.name}/{node.name}: {e}")
        print(f"[INFO] Shadow Color inputs set to white: {cnt}")

    def execute(self, context):
        sc = context.scene

        # 1) ch_vl → chCol_vl 이름만 변경(복제 금지)
        if getattr(self, "layer_choice", "RENAME") == 'RENAME':
            vls = sc.view_layers
            if "ch_vl" in vls:
                if "chCol_vl" in vls:
                    context.window.view_layer = vls["chCol_vl"]
                else:
                    vls["ch_vl"].name = "chCol_vl"
                    context.window.view_layer = vls["chCol_vl"]
            else:
                if "chCol_vl" in vls:
                    context.window.view_layer = vls["chCol_vl"]
                else:
                    new_vl = vls.new(name="chCol_vl")
                    context.window.view_layer = new_vl

        # 2) 커스텀 프로퍼티(Linear RGBA) 화이트로 강제
        WHITE4 = (1.0, 1.0, 1.0, 1.0)
        COLOR_KEYS = ("P02_Shadow_Color", "P01_Ambient_Color")

        for obj in bpy.data.objects:
            for k in COLOR_KEYS:
                self._ensure_color_idprop_rgba(obj, k, WHITE4)
        for k in COLOR_KEYS:
            self._ensure_color_idprop_rgba(sc, k, WHITE4)
        for w in bpy.data.worlds:
            for k in COLOR_KEYS:
                self._ensure_color_idprop_rgba(w, k, WHITE4)
        # 1.5) lightmask_vl 렌더 제외 (비활성화)
        for vl in sc.view_layers:
            if vl.name.startswith("chCol_"):
                vl.use = True
                print(f"[DEBUG] ViewLayer {vl.name} → ON")
            else:
                vl.use = False
                print(f"[DEBUG] ViewLayer {vl.name} → OFF") 
               
        # 2-추가) 머티리얼 노드 'Shadow Color' 소켓 화이트
        self._set_all_shadow_color_inputs_white()

        # 3) Output File Version - Current
        try:
            bpy.ops.sf.version_operator(increment=-999)
        except Exception as e:
            self.report({'WARNING'}, f"Version(Current) 실패: {e}")

        # 4) Output Path Settings - Custom='chCol' 적용
        try:
            if hasattr(sc, "my_tool"):
                sc.my_tool.custom_prefix = "chCol"
        except Exception:
            pass
        try:
            bpy.ops.sf.set_output_path(prefix="chCol")
        except Exception as e:
            self.report({'WARNING'}, f"Output Path 적용 실패: {e}")

        # 5) PNG 강제
        try:
            set_output_png(sc.render.image_settings, alpha=False, label="Color Pass: ")
        except Exception as e:
            self.report({'WARNING'}, f"PNG 설정 실패: {e}")

        self.report({'INFO'}, "Color Pass 완료: ch_vl→chCol_vl(이름만), 컬러/쉐도우 화이트, chCol 출력, PNG")
        return {'FINISHED'}

TARGET_PREFIX = "SF_Paint"

def _norm(s: str) -> str:
    return (s or "").lower().replace(" ", "").replace("_", "")

def _find_input(node, target_name: str):
    # 1) 정확히 일치
    if target_name in node.inputs:
        return node.inputs[target_name]

    # 2) 정규화 비교 (공백/언더스코어/대소문자 무시)
    tn = _norm(target_name)
    for s in node.inputs:
        if _norm(getattr(s, "name", "")) == tn:
            return s
    return None

def set_group_inputs_in_nodetree(nt, visited, target_prefix, value_map):
    """
    value_map 예:
      {"Strength": 0.2, "Mask_Int": 1.0, "Brusk_Int": 0.02, "Noise Int": 0.02}
    """
    if not nt:
        return 0

    nt_id = nt.as_pointer()
    if nt_id in visited:
        return 0
    visited.add(nt_id)

    changed = 0

    for node in nt.nodes:
        # 타겟 그룹 처리
        if node.type == 'GROUP' and node.node_tree and node.node_tree.name.startswith(target_prefix):
            for input_name, v in value_map.items():
                sock = _find_input(node, input_name)
                if sock is not None and hasattr(sock, "default_value"):
                    try:
                        sock.default_value = float(v)
                        changed += 1
                    except Exception:
                        pass

        # 중첩 그룹 재귀
        if node.type == 'GROUP' and node.node_tree:
            changed += set_group_inputs_in_nodetree(node.node_tree, visited, target_prefix, value_map)

    return changed



class SF_OT_ApplySFpaintGlobalControl(bpy.types.Operator):
    bl_idname = "sf.apply_sfpaint_global_control"
    bl_label = "Apply SFpaint Global Control"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        strength = float(context.scene.my_tool.sfpaint_emission_strength)
        mask_int = float(context.scene.my_tool.sfpaint_mask_int)
        brusk_int = float(context.scene.my_tool.sfpaint_brusk_int)
        noise_int = float(context.scene.my_tool.sfpaint_noise_int)

        value_map = {
            "Strength": strength,
            "Mask_Int": mask_int,
            "Brusk_Int": brusk_int,
            "Noise Int": noise_int,
        }

        visited = set()
        total_changed = 0
        for mat in bpy.data.materials:
            if not mat or not mat.use_nodes or not mat.node_tree:
                continue
            total_changed += set_group_inputs_in_nodetree(mat.node_tree, visited, TARGET_PREFIX, value_map)

        self.report({'INFO'}, f"[SF_Paint] updated sockets: {total_changed}")
        return {'FINISHED'}




import bpy

class SF_OT_ClearSelectedMaterials(bpy.types.Operator):
    bl_idname = "sf.clear_selected_materials"
    bl_label = "Clear Materials from Selected"
    bl_description = "선택된 오브젝트의 모든 메터리얼 슬롯을 제거합니다"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected = bpy.context.selected_objects
        if not selected:
            self.report({'INFO'}, "선택된 오브젝트가 없습니다.")
            return {'CANCELLED'}

        cleared_count = 0
        for obj in selected:
            if obj.type == 'MESH':
                obj.data.materials.clear()
                cleared_count += 1
                print(f"[OK] {obj.name} → 메터리얼 제거됨")

        self.report({'INFO'}, f"{cleared_count}개 오브젝트에서 메터리얼 제거 완료")
        return {'FINISHED'}
        
class SF_OT_ClearSelectedMaterialsPopup(bpy.types.Operator):
    bl_idname = "sf.clear_selected_materials_popup"
    bl_label = "Delete Materials on Selected"
    bl_description = "선택된 오브젝트의 모든 머티리얼을 삭제합니다 (확인 팝업 포함)"

    def invoke(self, context, event):
        # Blender 기본 확인 팝업 띄우기
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        # 실제 삭제 로직은 기존 오퍼레이터 호출
        bpy.ops.sf.clear_selected_materials('INVOKE_DEFAULT')
        self.report({'INFO'}, "✅ 선택한 오브젝트의 머티리얼이 모두 삭제되었습니다.")
        return {'FINISHED'}

class SF_OT_SetOutputFormat(bpy.types.Operator):
    bl_idname = "sf.set_output_format"
    bl_label = "Set Output Format"
    bl_description = "렌더 출력 포맷을 원클릭으로 설정합니다"

    format_type: bpy.props.StringProperty()

    def execute(self, context):
        sc = context.scene.render.image_settings

        if self.format_type == 'EXR':
            set_output_exr_multilayer(sc, label="Output Button EXR: ")
            self.report({'INFO'}, "Output Format: EXR Multilayer (RGBA, 16-bit)")

        elif self.format_type == 'PNG':
            set_output_png(sc, alpha=False, label="Output Button PNG: ")
            self.report({'INFO'}, "Output Format: PNG (RGB, 8-bit)")

        elif self.format_type == 'PNG_ALPHA':
            set_output_png(sc, alpha=True, label="Output Button PNG Alpha: ")
            self.report({'INFO'}, "Output Format: PNG with Alpha (RGBA, 8-bit)")

        return {'FINISHED'}

class SF_OT_DeleteSolidifyLine(bpy.types.Operator):
    bl_idname = "sf.delete_solidify_line"
    bl_label = "Delete Solidify Line"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        removed = []
        checked = 0

        print("\n" + "=" * 80)
        print("🔥 Solidify Modifier Flip ON 제거 시작")
        print(f"Scene: {scene.name}")
        print("=" * 80)

        for obj in scene.objects:
            if obj.type != 'MESH':
                continue

            for mod in list(obj.modifiers):
                if mod.type != 'SOLIDIFY':
                    continue

                checked += 1

                obj_name = obj.name
                mod_name = mod.name
                flip_on = bool(getattr(mod, "use_flip_normals", False))

                print(f"[CHECK] Object: {obj_name} / Modifier: {mod_name} / Flip: {flip_on}")

                if flip_on:
                    removed.append((obj_name, mod_name))
                    obj.modifiers.remove(mod)
                    print(f"  ✅ REMOVED: {obj_name} -> {mod_name}")

        print("=" * 80)
        print(f"검사한 Solidify Modifier 수: {checked}")
        print(f"삭제한 Modifier 수: {len(removed)}")

        if removed:
            print("\n삭제 목록:")
            for obj_name, mod_name in removed:
                print(f" - {obj_name} / {mod_name}")
        else:
            print("삭제할 Flip ON Solidify Modifier가 없습니다.")

        print("🔥 Solidify Modifier Flip ON 제거 완료")
        print("=" * 80 + "\n")

        self.report({'INFO'}, f"Delete Solidify Line 완료: {len(removed)}개 삭제")
        return {'FINISHED'}


################################################################
#########################UI#####################################
################################################################

# Scene Browser Panel (이건 기존처럼 단독 아코디언으로 유지)
class SF_PT_SceneBrowser(bpy.types.Panel):
    bl_label = "Scene Browser"
    bl_idname = "SF_PT_scene_browser"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SF_Render"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        my_tool = context.scene.my_tool
        project_settings = context.scene.my_project_settings

        box = layout.box()

        global last_mtime
        mtime = os.path.getmtime(SCRIPT_PATH) if os.path.exists(SCRIPT_PATH) else None
        script_path = os.path.abspath(__file__)
        last_modified = "File not found"
        try:
            mod_time = os.path.getmtime(script_path)
            last_modified = datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M")
        except OSError:
            pass

        row = layout.row()  
        row.scale_y = 0.8
        row.scale_x = 1
        row.alignment = 'CENTER'
        row.label(text=last_modified)         
        row.label(text="Storyfarm")

        row = box.row()        
        if last_mtime and mtime and mtime > last_mtime:
            row.alert = True
            row.scale_y = 1.6
            row.operator("dev.reload_rrrender", icon="FILE_REFRESH")
        else:
            row.scale_y = 1.6
            row.operator("dev.reload_rrrender", icon="FILE_REFRESH")
            
           
                      
        if can_show_deploy_tools():
            row = box.row()
            row.scale_y = 1.2
            row.operator("dev.deploy_rrrender", icon="EXPORT")

        row = box.row()
        row.prop(project_settings, "projects", text="Project")       
        row.operator("sf.refresh_scene_and_cut_cache", text="", icon="FILE_REFRESH")
        row = box.row()
        row.prop(my_tool, "scene_number")
        row.operator("sf.refresh_scene_and_cut_cache", text="", icon="FILE_REFRESH")
        row = box.row()
        row.prop(my_tool, "cut_number")
        row.operator("sf.refresh_scene_and_cut_cache", text="", icon="FILE_REFRESH")
        row = box.row()
        row.prop(my_tool, "blend_file")
        row.operator("file.open_cut_folder", text="", icon='FILE_FOLDER')
        row = box.row()
        row.scale_y = 1.3
        row.operator("file.open_file", text="Open") 
        row = box.row()
        row.operator("sf.save_render_scene", text="Save as v000")
        row.operator("sf.save_incremental_suffix", text="Incremental Save")
        
        # row = box.row(align=True)      
        # row.operator("sf.set_scene_from_file", text="Set Browser at Current Scene")    
        set_scene_settings()





# ==============================================================================
# ▼ 여기서부터 탭(Tab) 구성을 위한 '헬퍼 클래스'들 입니다. (기존 클래스 내용 100% 복붙)
# ==============================================================================

# --- [1. BUILD] Scene 구성 및 어셋 관리 ---
class SF_UI_BuildTab:
    @staticmethod
    def draw(layout, context):
        scene = context.scene
        
        box_main = layout.box()
        filename = os.path.basename(bpy.data.filepath) if bpy.data.filepath else "Untitled"
        box_main.label(text=filename, icon='FILE_BLEND')    
        
        row = box_main.row(align=True)        
        row.scale_y = 1.3
        row.operator("sf.build_scene_operator", text="Build Scene", icon='MOD_BUILD')
        row.operator("sf.view_layer_setup", text="Set ViewLayer", icon='RENDERLAYERS')

        row = box_main.row(align=True)
        row.prop(scene, "render_preset_enum", text="Preset")
        row.scale_x = 2
        row.operator("sf.apply_render_presets", text="", icon='CHECKMARK')
        
        box_list = layout.box()
        row_h = box_list.row(align=True)
        left_side = row_h.row(align=True)
        left_side.alignment = 'LEFT'
        left_side.label(text="Asset List", icon='ASSET_MANAGER')
        row_h.label(text="") 
        right_side = row_h.row(align=True)
        right_side.alignment = 'RIGHT'
        right_side.operator("sf.toggle_all_operator", text="", icon='CHECKBOX_HLT')
        right_side.operator("sf.generate_operator", text="", icon='FILE_REFRESH')
        right_side.operator("sf.import_scene_camera", text="", icon='VIEW_CAMERA')

        sorted_categories = sorted(scene.sf_file_categories, key=lambda cat: cat.name)
        if sorted_categories:
            # 💡 [핵심] 박스 간의 여백을 없애기 위해 align=True 컬럼으로 한 번 감싸줍니다.
            categories_col = box_list.column(align=True)
            
            for category in sorted_categories:
                cat_container = categories_col.box()
                split = cat_container.split(factor=0.1, align=True) 
                
                col1 = split.column(align=True)
                col1.alignment = 'LEFT'
                display_name = "PR" if category.name.upper() == "PROP" else category.name.upper()
                op = col1.operator("sf.toggle_category_operator", text=display_name, emboss=False)
                op.category_name = category.name
                
                col2 = split.column(align=True)
                col2.scale_y = 1.0
                sorted_items = sorted(category.items, key=lambda item: item.name)
                for i in range(0, len(sorted_items), 2):
                    item_row = col2.row(align=True)
                    for j in range(2):
                        if i + j < len(sorted_items):
                            item = sorted_items[i + j]
                            item_row.prop(item, "is_selected", text=item.name, toggle=True)
                        else:
                            item_row.label(text="")
        else:
            box_list.label(text="No Assets Generated.", icon='INFO')
            
        row_imp = box_list.row(align=True)
        row_imp.scale_y = 1.7
        project = scene.my_project_settings.projects
        if project in ['DSC', 'THE_TRAP', 'ARBOBION', 'BTS']:
            row_imp.operator("sf.import_and_update_operator_dsc", text="IMPORT ASSET", icon='IMPORT')
        else:
            row_imp.operator("sf.import_selected_operator", text="IMPORT (Legacy)", icon='IMPORT')

        box_update = layout.box()
        box_update.label(text="Update Asset", icon='FILE_REFRESH')
        row = box_update.row(align=True)
        row.scale_y = 1.3
        row.operator("sf.update_selected_operator_dsc", text="Sync Cache", icon='FILE_REFRESH')
        row.operator("sf.update_from_publish", text="Reset to Pub", icon='FILE_BACKUP')
        
        box_tools = layout.box()        
        # box_update = layout.box()
        box_tools.label(text="Shader Tools", icon='SHADING_RENDERED')
        row = box_tools.row(align=True)
        row.scale_y = 1.3
        row.operator("sf.all_in_one", text="ReCore Mat", icon='SHADING_RENDERED')
        row.operator("object.sf_link_light_properties", text="ReLink Light", icon='DRIVER')

        # box_tools = layout.box()
        # icon = 'TRIA_DOWN' if scene.sf_show_advanced else 'TRIA_RIGHT'
        # box_tools.prop(scene, "sf_show_advanced", icon=icon, text="Tools", emboss=False)

        # if scene.sf_show_advanced:



# --- [2. OUTPUT] 렌더 범위 ~ 렌더 프리셋 ---
class SF_UI_OutputTab:
    @staticmethod
    def draw(layout, context):
        scene = context.scene
        
        box = layout.box()
        box.label(text="Render Range", icon='PREVIEW_RANGE')
        row = box.row(align=True)
        row.operator("frame.range_operator", text="Full").option = "FULL"
        row.operator("frame.range_operator", text="Current Still").option = "CURRENT"

        box = layout.box()
        box.label(text="Output File Version", icon='FILE_NEW')
        row = box.row(align=True)
        row.operator("sf.version_operator", text="Dn").increment = -1
        row.operator("sf.version_operator", text="Current").increment = -999
        row.operator("sf.version_operator", text="Up").increment = 1
        
        box = layout.box()
        box.label(text="Output Path Settings", icon='FILE_FOLDER')
        row = box.row(align=True)
        row.operator("sf.set_output_path", text="ch").prefix = "ch"
        row.operator("sf.set_output_path", text="bg").prefix = "bg"
        row.operator("sf.set_output_path", text="line").prefix = "line"
        row.operator("sf.set_output_path", text="prop").prefix = "prop"
        row = box.row(align=True)
        row.prop(context.scene.my_tool, "custom_prefix", text="Custom")
        row.operator("sf.set_output_path", text="", icon='CHECKMARK').prefix = context.scene.my_tool.custom_prefix
        
        row_format = box.row(align=True)
        row_format.operator("sf.set_output_format", text="EXR").format_type = 'EXR'
        row_format.operator("sf.set_output_format", text="PNG").format_type = 'PNG'
        row_format.operator("sf.set_output_format", text="PNG (Alpha)").format_type = 'PNG_ALPHA'
 
        box_preset = layout.box()
        box_preset.label(text="Render Presets", icon='PRESET')
        row = box_preset.row(align=True)
        row.operator("render.set_cycles_render_settings", text="Denoise")
        row = box_preset.row(align=True)
        row.operator("sf.set_light_bounces", text="Fix Light Bounce to 1024")

        box_render = layout.box()
        box_render.label(text="Rendering", icon='RESTRICT_RENDER_OFF')
        row_submit = box_render.row()
        row_submit.scale_y = 1.5
        row_submit.operator("wm.submit_blender_to_deadline", text="Submit to Deadline")




# --- [3. CACHE] 애니메이션 및 캐시 (위치 변경!) ---
class SF_UI_CacheTab:
    @staticmethod
    def draw(layout, context):
        box_ani = layout.box()
        box_ani.label(text="2 Comma Ani", icon='ANIM_DATA')
        row = box_ani.row(align=True)
        row.operator("object.make_2com", text="Make 2Com")
        row.operator("object.del_2com", text="Del 2Com")

        box_cash = layout.box()
        box_cash.label(text="Cash Tools", icon='SHAPEKEY_DATA')
        row = box_cash.row(align=True)
        row.operator("object.bake_shape_keys", text="Bake to ShapeKey")


# --- [4. MASK / PASS] 마스크들과 패스 생성 통합 (위치 변경!) ---
class SF_UI_MaskPassTab:
    @staticmethod
    def draw(layout, context):
        scene = context.scene

        box = layout.box()
        box.label(text="Light Mask", icon='LIGHT')
        row = box.row(align=True)
        row.operator("object.apply_light_mask", text="Add")
        row.operator("object.update_light_mask", text="Update")
        row.operator("object.remove_light_mask", text="Remove")
        row = box.row(align=True)     
        row.operator("object.make_shared_unique_material", text="Material Unique Selected")

        box = layout.box()
        box.label(text="Caustics Mask", icon='MOD_FLUIDSIM')
        row = box.row(align=True)
        row.operator("object.apply_caustics_mask", text="Add")
        row.operator("object.remove_caustics_mask", text="Remove")

        box = layout.box()
        box.label(text="Color Pass", icon='COLOR')        
        row_pass = box.row()
        row_pass.scale_y = 1.3
        row_pass.operator("sf.make_color_pass", text="Make Color Pass")
        
        box = layout.box()
        box.label(text="Set Ch Blocker", icon='MESH_CUBE')
        row = box.row(align=True)
        row.operator("object.apply_blocker", text="Add")
        row.operator("object.remove_blocker", text="Remove")

        box = layout.box()
        box.label(text="Set Shadow Catcher", icon='SHADING_RENDERED')
        row = box.row(align=True)
        row.operator("object.apply_shadow_catcher", text="Add")
        row.operator("object.remove_shadow_catcher", text="Remove")


# --- [5. OUTLINE] 라인 작업 ---
class SF_UI_OutlineTab:
    @staticmethod
    def draw(layout, context):
        box = layout.box()
        box.label(text="SF_OutputLine", icon="GREASEPENCIL")
        row = box.row(align=True)
        row.operator("object.sf_update_to_cycles_independent", text="Make Outline")  
        row = box.row(align=True)
        row.operator("object.sf_bake_outline", text="Bake Outline")
        row.operator("object.sf_clear_bake_outline", text="Clear Bake")


# --- [6. TOOLS] 클린업 툴 & SFpaint ---
class SF_UI_ToolsTab:
    @staticmethod
    def draw(layout, context):
        scene = context.scene
        
        # (상단 CleanUp Tools 박스 등은 그대로 유지)
        box = layout.box()
        box.label(text="CleanUp Tools", icon='BRUSH_DATA')
        row = box.row(align=True)
        row.operator("sf.subdivide_class", text="SubdivAll")
        row.operator("sf.unsubdivide_class", text="UnSubdivAll")
        row = box.row(align=True)  
        row.operator("sf.cleanup_orphans_combined1", text="CleanUp Mat") 
        row.operator("object.delete_non_visible_meshes", text="Del Invisible")
        row = box.row(align=True)           
        row.operator("sf.clear_selected_materials_popup", text="Delete Material on Selected", icon='TRASH') 
        row.operator("sf.delete_solidify_line", text="Delete Solidify Line", icon='TRASH')
        row = box.row(align=True)   
        row.operator("object.replace_botaniq_library_path", text="RePath Botaniq")
        row.operator("object.replace_sanctus_library_path", text="RePath sanctus")        

        # 🔥 여기서부터 수정된 SFpaint Global Control 부분 🔥
        box_paint = layout.box()
        box_paint.label(text="SFpaint Global Control", icon='NODETREE')
        
        # 1. 수치 입력칸 4개 깔끔하게 정렬
        row = box_paint.row(align=True)
        row.label(text="Emit")
        row.prop(context.scene.my_tool, "sfpaint_emission_strength", text="")

        row = box_paint.row(align=True)
        row.label(text="Mask_Int")
        row.prop(context.scene.my_tool, "sfpaint_mask_int", text="")

        row = box_paint.row(align=True)
        row.label(text="Brusk_Int")
        row.prop(context.scene.my_tool, "sfpaint_brusk_int", text="")

        row = box_paint.row(align=True)
        row.label(text="Noise Int")
        row.prop(context.scene.my_tool, "sfpaint_noise_int", text="")

        # 2. 맨 아래에 전체 적용(Apply) 버튼을 크고 시원하게 배치!
        box_paint.separator(factor=0.5)
        row_apply = box_paint.row()
        row_apply.scale_y = 1.3
        row_apply.operator("sf.apply_sfpaint_global_control", text="Apply All SFpaint Settings", icon='CHECKMARK')


# ==============================================================================
# ▼ 메인 탭 패널 (Render Tools)
# ==============================================================================
class SF_PT_MainTabPanel(bpy.types.Panel):
    bl_label = "Render Tools"
    bl_idname = "SF_PT_main_tab_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SF_Render"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        col = layout.column(align=True)
        
        # --- 1행 (CACHE를 위로 올림) ---
        row1 = col.row(align=True)
        row1.scale_y = 1.6
        row1.prop_enum(scene, "sf_active_tab", 'BUILD')
        row1.prop_enum(scene, "sf_active_tab", 'OUTPUT')
        row1.prop_enum(scene, "sf_active_tab", 'CACHE') 
        
        # --- 2행 (MASK_PASS를 아래로 내림) ---
        row2 = col.row(align=True)
        row2.scale_y = 1.6
        row2.prop_enum(scene, "sf_active_tab", 'MASK_PASS') 
        row2.prop_enum(scene, "sf_active_tab", 'OUTLINE')
        row2.prop_enum(scene, "sf_active_tab", 'TOOLS')
        
        layout.separator(factor=0.5)
        
        # 선택된 탭 분기
        tab = scene.sf_active_tab
        if tab == 'BUILD':
            SF_UI_BuildTab.draw(layout, context)
        elif tab == 'OUTPUT':
            SF_UI_OutputTab.draw(layout, context)
        elif tab == 'MASK_PASS':
            SF_UI_MaskPassTab.draw(layout, context)
        elif tab == 'CACHE':
            SF_UI_CacheTab.draw(layout, context)
        elif tab == 'OUTLINE':
            SF_UI_OutlineTab.draw(layout, context)
        elif tab == 'TOOLS':
            SF_UI_ToolsTab.draw(layout, context)
           
# 아이템 객체 정의
class FileNameItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")
    is_selected: bpy.props.BoolProperty(name="Is Selected", default=True)
    exist_in_scene: bpy.props.BoolProperty(name="Exist in Scene", default=False)

# 카테고리 객체 정의
class FileCategory(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")
    items: bpy.props.CollectionProperty(type=FileNameItem)
    is_selected: bpy.props.BoolProperty(name="Select All", default=False)

# 카테고리 선택 시 모든 아이템을 선택/해제하는 연산자 정의
class SF_OT_ToggleCategory(bpy.types.Operator):
    bl_idname = "sf.toggle_category_operator"
    bl_label = "Toggle Category Selection"
    
    category_name: bpy.props.StringProperty()
    
    def execute(self, context):
        category = next((cat for cat in context.scene.sf_file_categories if cat.name == self.category_name), None)
        if category:
            new_state = not category.is_selected
            category.is_selected = new_state
            for item in category.items:
                item.is_selected = new_state
        return {'FINISHED'}

# 모든 항목 선택/해제 연산자 정의
class SF_OT_ToggleAllOperator(bpy.types.Operator):
    bl_idname = "sf.toggle_all_operator"
    bl_label = "Toggle All"
    
    def execute(self, context):
        all_selected = all(item.is_selected for category in context.scene.sf_file_categories for item in category.items)
        
        for category in context.scene.sf_file_categories:
            for item in category.items:
                item.is_selected = not all_selected
        return {'FINISHED'}

def auto_set_browser_fields():
    import bpy, os
    filepath = bpy.data.filepath.replace("\\", "/")
    parts = filepath.split("/")

    if len(parts) < 5:
        print("[WARN] 경로 구조가 예상과 다름:", filepath)
        return

    scene_number = parts[2]
    cut_number   = parts[3]
    blend_file_name = os.path.basename(filepath)                 # DSC_0100_0230_ren_v002_ch.blend
    blend_file_noext = os.path.splitext(blend_file_name)[0]      # DSC_0100_0230_ren_v002_ch

    print(f"[INFO] 현재 파일 기준 자동 설정 → scene: {scene_number}, cut: {cut_number}, file: {blend_file_name}")

    scene = bpy.context.scene
    if hasattr(scene, "my_tool"):
        props = scene.my_tool
        props.scene_number = scene_number
        props.cut_number   = cut_number

        # --- blend_file Enum 값 파싱 ---
        tokens = blend_file_noext.split("_")
        enum_value = "_".join(tokens[-2:]) if len(tokens) >= 2 else blend_file_noext

        # --- 실제 Enum 목록에 있는 경우만 대입 ---
        if hasattr(props, "blend_file_items"):
            enum_items = [i[0] for i in props.blend_file_items]
            if enum_value in enum_items:
                props.blend_file = enum_value
                print(f"[AUTOSET] blend_file set to '{enum_value}'")
            else:
                print(f"[WARN] enum '{enum_value}' not in {enum_items}")
        else:
            props.blend_file = enum_value  # fallback (enum_items 없음)


class SF_OT_DisableOutline(bpy.types.Operator):
    bl_idname = "sf.disable_outline"
    bl_label = "Disable SF_Outline"
    bl_description = "씬 내 모든 SF_Outline 모디파이어 끄기"

    def execute(self, context):
        count = 0
        for obj in bpy.data.objects:
            for mod in obj.modifiers:
                if mod.name == "SF_Outline":
                    mod.show_viewport = False
                    mod.show_render = False
                    count += 1
        self.report({'INFO'}, f"Disabled {count} SF_Outline modifiers.")
        return {'FINISHED'}


# 🔹 SF_Outline 모디파이어 켜기
class SF_OT_EnableOutline(bpy.types.Operator):
    bl_idname = "sf.enable_outline"
    bl_label = "Enable SF_Outline"
    bl_description = "씬 내 모든 SF_Outline 모디파이어 켜기"

    def execute(self, context):
        count = 0
        for obj in bpy.data.objects:
            for mod in obj.modifiers:
                if mod.name == "SF_Outline":
                    mod.show_viewport = True
                    mod.show_render = True
                    count += 1
        self.report({'INFO'}, f"Enabled {count} SF_Outline modifiers.")
        return {'FINISHED'}


################################################################
######################### Register #############################
################################################################
bpy.types.Scene.input_15 = bpy.props.FloatProperty(name="Input 15", default=0.001)
bpy.types.Scene.input_16 = bpy.props.FloatProperty(name="Input 16", default=0.08)


# ✅ 등록할 클래스 리스트
# ✅ 등록할 클래스 리스트 정리
classes = [
    OBJECT_OT_make_2com,
    OBJECT_OT_del_2com,
    SF_OT_GenerateOperator,
    SF_OT_LinkSelectedOperator,
    SF_OT_LinkAllOperator,
    SF_OT_ImportSelectedOperator,
    SF_OT_ToggleAllOperator,
    SF_OT_BuildSceneOperator,
    FileNameItem,
    FileCategory,
    SF_OT_ImportSceneCameraOperator,
    SF_CleanupOrphansCombined,
    SF_SaveRenderScene,
    SF_OT_UpdateMaterialsOperator,
    LinkClass,
    SubdivideClass,
    SF_OT_VersionOperator,
    IncrementalSaveOperator,
    LineArtGenerator,
    SF_OT_ApplyLineArt,
    MyProperties,
    OpenSceneFolderOperator,
    OpenCutFolderOperator,
    OpenFileOperator,
    AppendSceneOperator,
    WM_OT_ReinstallAddon1,
    SF_OT_ApplyPreset,
    SF_OT_RenderSetting,
    SF_PT_SceneBrowser,
    SF_PT_MainTabPanel, # 👈 3개 대신 이거 하나만 등록! (Main Tools -> Render Tools)
    SF_OT_RefreshDriverDependencies,
    SF_OT_GetSelectedAssetsOperator,
    MyProjectSettings1,
    SF_OT_UpdateSelectedOperator,
    SF_OT_UpdateSelectedLightOperator,
    SF_OT_ClearCustomNormalOperator,
    UpdateLightPosition,
    SF_OT_SetStaticBG,
    SF_OT_SetMovingBG,
    SF_OT_AddPropertiesAndLink1,
    SF_OT_LinkCharacterLights1,
    SF_OT_LinkRimToNode1,
    SF_OT_SetViewLayerMode,
    SubmitBlenderToDeadline,
    FrameRangeOperator,
    CameraMovementFrameRangeOperator,
    SimpleSceneProps,
    OBJECT_OT_apply_shadow_catcher,
    OBJECT_OT_remove_shadow_catcher,
    SF_OT_ResetMaterialOperator,
    SF_OT_updateMaterialOperator,
    OBJECT_OT_apply_blocker,
    OBJECT_OT_remove_blocker,
    OBJECT_OT_remove_light_mask,
    OBJECT_OT_apply_light_mask,
    SF_OT_ApplyRenderPresets,
    BakeShapeKeysOperator,
    OBJECT_OT_apply_caustics_mask,
    OBJECT_OT_remove_caustics_mask,
    SF_OT_ToggleCategory,
    DeleteNonVisibleMeshesOperator,
    ReplaceBotaniqLibraryPathOperator,
    ReplacesanctusLibraryPathOperator,
    SetCyclesRenderSettings,
    unSubdivideClass,
    DeleteAllFakeUsersOperator,
    NodeGroupLinkerOperator,
    OBJECT_OT_make_shared_unique_material,
    OBJECT_OT_update_light_mask,
    OBJECT_OT_update_shadow_material,
    SF_OT_CopyDropletGeneratorOperator,
    SF_OT_RemoveDropletGeneratorOperator,
    OBJECT_OT_instance_solidify,
    SF_OT_UpdateSelectedOperatorDSC,
    SF_OT_ImportSelectedOperatorDSC,
    SF_OT_RefreshSceneAndCutCache,
    SF_MaterialSwitcherProperties, 
    SF_OT_ImportAndUpdateOperatorDSC,
    SF_OT_SetSceneFromFile,
    SF_OT_DisableOutline,
    SF_OT_EnableOutline,
    SF_OT_UpdateToCyclesIndependent,
    SF_OT_BakeOutline,
    SF_OT_UpdateFromPublish,
    SF_OT_SetOutputPath,
    SF_OT_SaveIncrementalSuffix,
    DEV_OT_reload_rrrender,
    DEV_OT_deploy_rrrender,
    SF_OT_ImportModePopup,
    SF_OT_LinkLightProperties,
    SF_OT_AllInOne,
    SF_OT_ClearBakeOutline,
    SF_OT_ViewLayerSetupOperator,
    SF_OT_SetLightBounces,
    SF_OT_MakeColorPass,
    SF_OT_ClearSelectedMaterials,
    SF_OT_ClearSelectedMaterialsPopup,
    SF_OT_ApplySFpaintGlobalControl,
    SF_OT_SetOutputFormat,
    SF_OT_DeleteSolidifyLine,
    OBJECT_OT_remove_shell
]

_auto_browser_timer = None  # 전역 변수로 선언

def register():
    # ✅ 1. 6개 탭 아이콘 및 순서 재배치 (CACHE ↔ MASK_PASS)
    bpy.types.Scene.sf_active_tab = bpy.props.EnumProperty(
        items=[
            ('BUILD', "Build", "Scene Build & Assets", 'MOD_BUILD', 0),
            ('OUTPUT', "Output", "Output & Render Settings", 'FILE_FOLDER', 1),
            ('CACHE', "Ani/Bake", "Cache & Animation Tools", 'PHYSICS', 2), # 👈 순서 변경됨
            ('MASK_PASS', "Mask/Pass", "Masks & Passes", 'RENDERLAYERS', 3), # 👈 순서 변경됨
            ('OUTLINE', "Outline", "Outline Settings", 'GREASEPENCIL', 4),
            ('TOOLS', "Tools", "Extra Tools", 'SETTINGS', 5)
        ],
        default='BUILD'
    )
        
    global _auto_browser_timer

    # ✅ 2. 모든 클래스 일괄 등록
    for cls in classes:
        bpy.utils.register_class(cls)

    # ✅ 3. Scene 프로퍼티 및 포인터 연결
    bpy.types.Scene.my_tool = bpy.props.PointerProperty(type=MyProperties)
    bpy.types.Scene.my_project_settings = bpy.props.PointerProperty(type=MyProjectSettings1)
    bpy.types.Scene.simple_scene_props = bpy.props.PointerProperty(type=SimpleSceneProps)
    bpy.types.Scene.sf_scene_number = bpy.props.StringProperty(name="Scene Number", default="0010")
    bpy.types.Scene.sf_cut_number = bpy.props.StringProperty(name="Cut Number", default="0010")
    bpy.types.Scene.sf_message = bpy.props.StringProperty(default="")
    bpy.types.Scene.sf_file_categories = bpy.props.CollectionProperty(type=FileCategory)
    bpy.types.Scene.sf_mat_switcher = bpy.props.PointerProperty(type=SF_MaterialSwitcherProperties)
    bpy.types.Scene.sf_show_advanced = bpy.props.BoolProperty(name="Show Tools", default=False)
    
    bpy.types.Scene.render_preset_enum = bpy.props.EnumProperty(
        name="Render Preset",
        description="Choose a render preset",
        items=get_preset_items
    )    

    # ✅ 4. 메뉴 및 핸들러 등록
    bpy.types.TOPBAR_MT_render.append(menu_func)

    if run_set_scene_from_file not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(run_set_scene_from_file)

    _auto_browser_timer = bpy.app.timers.register(auto_set_browser_fields, first_interval=0.5)
    register_scene_loader_handler()


def unregister():
    global _auto_browser_timer

    # ✅ 1. 타이머 완전 해제
    if _auto_browser_timer:
        try:
            bpy.app.timers.unregister(auto_set_browser_fields)
        except Exception:
            pass
        _auto_browser_timer = None

    # ✅ 2. 메뉴 해제
    try:
        bpy.types.TOPBAR_MT_render.remove(menu_func)
    except Exception:
        pass

    # ✅ 3. 클래스 해제 (반드시 역순으로)
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

    # ✅ 4. Scene 프로퍼티 찌꺼기 완벽 제거 (새로 만든 탭 변수 포함!)
    scene_props = [
        "sf_active_tab",      # <--- 새로 생긴 6개 탭 변수 삭제 추가!
        "my_tool",
        "my_project_settings",
        "simple_scene_props",
        "sf_scene_number",
        "sf_cut_number",
        "sf_message",
        "sf_file_categories",
        "sf_mat_switcher",
        "sf_show_advanced",   # <--- 이것도 확실히 지워줍니다.
        "render_preset_enum",
    ]
    for prop_name in scene_props:
        if hasattr(bpy.types.Scene, prop_name):
            try:
                delattr(bpy.types.Scene, prop_name)
            except Exception:
                pass

    # ✅ 5. 핸들러 해제
    if run_set_scene_from_file in bpy.app.handlers.load_post:
        try:
            bpy.app.handlers.load_post.remove(run_set_scene_from_file)
        except Exception:
            pass


def load_post_handler(dummy):
    import bpy
    filepath = bpy.data.filepath
    scene_number, cut_number = extract_scene_cut_from_filename(filepath)

    if scene_number and cut_number:
        scene = bpy.context.scene
        if hasattr(scene, "my_tool") and hasattr(scene.my_tool, "scene_number") and hasattr(scene.my_tool, "cut_number"):
            scene.my_tool.scene_number = scene_number
            scene.my_tool.cut_number = cut_number
            print(f"[LOAD] 씬/컷 자동 설정됨: {scene_number} / {cut_number}")

            # ✅ UI 강제 새로고침 (기존 PROPERTIES 뿐만 아니라 VIEW_3D 창도 새로고침!)
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type in {'PROPERTIES', 'VIEW_3D'}:
                        area.tag_redraw()
        else:
            print("[LOAD] my_tool 속성 또는 필드가 없음: 씬/컷 설정 생략됨.")
# 핸들러 중복 방지 후 append
for h in bpy.app.handlers.load_post:
    if h.__name__ == 'load_post_handler':
        break
else:
    bpy.app.handlers.load_post.append(load_post_handler)


if __name__ == "__main__":

    register()
    unregister()

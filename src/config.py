"""
配置管理模块
定义全局配置常量和默认限值
"""

import os
from typing import Dict, List

# 路径配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, 'templates')
RESULT_DIR = os.path.join(PROJECT_ROOT, 'result')
MODELS_DIR = os.path.join(PROJECT_ROOT, 'models')

# 确保目录存在
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

# 标准分类（键为英文目录名）
STANDARDS: Dict[str, Dict[str, str]] = {
    'GB3883': {
        'name': 'GB 3883.1-2014',
        'description': '手持式、可移式电动工具和园林工具的安全 第1部分：通用要求',
    },
    'GB4208': {
        'name': 'GB/T 4208-2017',
        'description': '外壳防护等级（IP 代码）',
    },
    'GB3883_2XX': {
        'name': 'GB/T 3883.2XX',
        'description': '手持式电动工具的专用要求（第2部分）',
    },
    'GB3883_3XX': {
        'name': 'GB/T 3883.3XX',
        'description': '可移式电动工具的专用要求（第3部分）',
    },
    'GB3883_4XX': {
        'name': 'GB/T 3883.4XX',
        'description': '园林工具的专用要求（第4部分）',
    },
    'GB4343': {
        'name': 'GB 4343.1-2024',
        'description': '电磁兼容 家用电器、电动工具和类似器具的要求 第1部分：发射',
    },
    'GB17625': {
        'name': 'GB 17625.1-2023',
        'description': '电磁兼容 限值 谐波电流发射限值',
    },
}

# 测试类型分类配置（内部英文键）
TEST_CATEGORIES: Dict[str, List[str]] = {
    '通用测试': [
        'clause12_heating',
        'gb4343_1_emission',
        'clause25_power_cord_bending',
    ],
}


# 模板中文显示名称（UI 使用）
TEMPLATE_DISPLAY_NAMES: Dict[str, str] = {
    # 通用测试
    'clause11_input_power_current': '输入功率和电流',
    'clause12_heating': '发热',
    'clause26_earthing': '接地装置',
    'appendix_d_dielectric_strength': '电气强度与绝缘电阻',
    'appendix_c_leakage_current': '泄漏电流',
    'clause20_mechanical_strength': '机械强度',
    'ip_rating': '外壳防护等级',
    'clause25_power_cord_bending': '电缆弯曲测试',
    'gb4343_1_emission': 'EMC',
    # 手持式电动工具专用
    'gb3883_201_drill': '电钻',
    'gb3883_202_screwdriver': '螺丝刀',
    'gb3883_222_impact_wrench': '冲击扳手',
    'gb3883_203_grinder': '砂轮机',
    'gb3883_204_sander': '非盘式砂光机',
    'gb3883_205_circular_saw': '圆锯',
    'gb3883_206_rotary_hammer': '电锤',
    'gb3883_207_planer': '电刨',
    'gb3883_208_shear_and_nibbler': '电剪刀和电冲剪',
    'gb3883_209_tapper': '攻丝机',
    'gb3883_210_chain_saw': '电链锯',
    'gb3883_211_reciprocating_saw': '往复锯',
    'gb3883_212_concrete_vibrator': '混凝土振动器',
    'gb3883_213_spray_gun': '电喷枪',
    'gb3883_214_pruning_shear': '修枝剪',
    'gb3883_215_hedge_trimmer': '树篱修剪机',
    'gb3883_216_band_saw': '带锯',
    'gb3883_217_router_and_trimmer': '木铣和修边机',
    'gb3883_218_strapping_tool': '捆扎机',
    'gb3883_221_grass_shear': '手持式剪草机',
    # 可移式电动工具专用
    'gb3883_301_general_transportable': '可移式工具通用要求',
    'gb3883_302_transportable_table_saw': '可移式台锯',
    'gb3883_303_planer_and_thicknesser': '平刨和压刨',
    'gb3883_304_transportable_band_saw': '可移式带锯',
    'gb3883_305_transportable_liquid_pump': '可移式液体泵',
    'gb3883_306_diamond_core_drill': '金刚石钻',
    'gb3883_307_transportable_grinder': '可移式砂轮机',
    'gb3883_309_transportable_mitre_saw': '可移式斜切锯',
    # 园林工具
    'gb3883_401_chain_saw': '电链锯',
    'gb3883_404_lawn_mower': '电动割草机',
    # EMC 测试
    'gb4343_1_emission': 'EMC',
    'gb17625_1_harmonic_current': '谐波电流',
    'gb17625_2_voltage_flicker': '电压波动和闪烁',
}

# 默认限值配置（可被模板覆盖）
DEFAULT_LIMITS: Dict[str, Dict[str, float]] = {
    'clause12_heating': {
        'stator_max': 80.0,
        'rotor_max': 95.0,
        'bearing_max': 75.0,
        'brush_max': 85.0,
    },
    'appendix_d_dielectric_strength': {
        'leakage_current_max': 5.0,
        'test_voltage_min': 3000.0,
    },
    'clause26_earthing': {
        'resistance_max': 0.1,
        'test_current_min': 25.0,
    },
    'appendix_c_leakage_current': {
        'current_max': 0.75,
    },
    'clause11_input_power_current': {
        'deviation_max': 10.0,
    },
}

# 容差配置
TOLERANCE: Dict[str, float] = {
    'temperature_rise': 0.5,
    'numeric': 0.5,
    'calculation': 0.5,
}

# OCR 配置
OCR_CONFIG: Dict[str, bool] = {
    'use_angle_cls': True,
    'lang': 'ch',
    'use_gpu': False,
}

# 模板字段类型
FIELD_TYPES: List[str] = ['number', 'text', 'date']

# 错误级别
ERROR_LEVELS: Dict[str, str] = {
    'info': '信息',
    'warning': '警告',
    'error': '错误',
}

# GUI 配置
GUI_CONFIG: Dict[str, int] = {
    'window_width': 1200,
    'window_height': 800,
    'pdf_width': 700,
    'pdf_height': 500,
}


def get_template_path(template_name: str) -> str:
    """
    获取指定测试类型的模板文件路径
    支持按标准子目录查找（含递归子目录）
    
    Args:
        template_name: 模板名称（英文键）
        
    Returns:
        模板文件路径
    """
    # 先在根目录查找
    root_path = os.path.join(TEMPLATES_DIR, f'{template_name}.json')
    if os.path.exists(root_path):
        return root_path
    
    # 在各标准子目录查找（含递归子目录）
    for standard_dir in STANDARDS.keys():
        std_path = os.path.join(TEMPLATES_DIR, standard_dir, f'{template_name}.json')
        if os.path.exists(std_path):
            return std_path
        # 递归查找子目录（如 GB3883_2XX, GB3883_3XX）
        if os.path.isdir(os.path.join(TEMPLATES_DIR, standard_dir)):
            for subname in os.listdir(os.path.join(TEMPLATES_DIR, standard_dir)):
                subdir = os.path.join(TEMPLATES_DIR, standard_dir, subname)
                if os.path.isdir(subdir):
                    sub_path = os.path.join(subdir, f'{template_name}.json')
                    if os.path.exists(sub_path):
                        return sub_path
    
    # 默认返回 GB3883 目录下的路径
    return os.path.join(TEMPLATES_DIR, 'GB3883', f'{template_name}.json')


def get_template_display_name(template_name: str) -> str:
    """
    获取模板的中文显示名称
    
    Args:
        template_name: 模板英文键
        
    Returns:
        中文显示名称；若未配置则返回原始键
    """
    return TEMPLATE_DISPLAY_NAMES.get(template_name, template_name)


def get_result_path(document_name: str) -> str:
    """
    获取校验结果文件路径
    
    Args:
        document_name: 文档文件名（不含扩展名）
        
    Returns:
        结果文件路径
    """
    return os.path.join(RESULT_DIR, f'{document_name}_result.json')


def list_available_templates() -> List[str]:
    """
    列出所有可用的模板文件（递归扫描所有子目录）
    
    Returns:
        模板文件名列表（不含扩展名，英文键）
    """
    templates = []
    
    def scan_dir(directory):
        """递归扫描目录下的JSON文件"""
        if not os.path.exists(directory):
            return
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path) and item.endswith('.json'):
                templates.append(os.path.splitext(item)[0])
            elif os.path.isdir(item_path):
                scan_dir(item_path)
    
    scan_dir(TEMPLATES_DIR)
    
    return sorted(set(templates))


if __name__ == "__main__":
    print(f"模板目录: {TEMPLATES_DIR}")
    print(f"可用模板: {list_available_templates()}")
    print(f"默认限值: {DEFAULT_LIMITS}")

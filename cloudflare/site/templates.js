/* 自动生成，请勿手工编辑。来源：templates/（共 3 个模板） */
window.REPORT_TEMPLATES = [
  {
    "name": "clause12_heating",
    "standard": "GB 3883.1-2014",
    "standard_dir": "GB3883",
    "title": "发热",
    "description": "温升试验",
    "display": "发热",
    "template": {
      "standard": "GB 3883.1-2014",
      "clause": "12",
      "title": "发热",
      "description": "温升试验",
      "version": "2.1",
      "tables": [
        {
          "title": "输入输出参数",
          "data_grid": true,
          "headers": [
            {
              "label": "电压U(V)"
            },
            {
              "label": "频率f(Hz)"
            },
            {
              "label": "电流I(A)"
            },
            {
              "label": "输入功率P1(W)"
            },
            {
              "label": "输出功率P2(W)"
            },
            {
              "label": "转速n(r/min)"
            },
            {
              "label": "转矩T(N·m)"
            },
            {
              "label": "效率η(%)"
            },
            {
              "label": "功率因素cosφ"
            }
          ],
          "fields": [
            {
              "name": "no_load",
              "type": "number_array",
              "description": "空载",
              "array_size": 9,
              "unit": ""
            },
            {
              "name": "rated_load_1",
              "type": "number_array",
              "description": "额定负载1",
              "array_size": 9,
              "unit": "",
              "show_label": true
            },
            {
              "name": "rated_load_2",
              "type": "number_array",
              "description": "额定负载2",
              "array_size": 9,
              "unit": "",
              "show_label": true
            },
            {
              "name": "voltage_0_94_1",
              "type": "number_array",
              "description": "0.94倍额定电压1",
              "array_size": 9,
              "unit": "",
              "show_label": true
            },
            {
              "name": "voltage_0_94_2",
              "type": "number_array",
              "description": "0.94倍额定电压2",
              "array_size": 9,
              "unit": "",
              "show_label": true
            },
            {
              "name": "voltage_1_06_1",
              "type": "number_array",
              "description": "1.06倍额定电压1",
              "array_size": 9,
              "unit": "",
              "show_label": true
            },
            {
              "name": "voltage_1_06_2",
              "type": "number_array",
              "description": "1.06倍额定电压2",
              "array_size": 9,
              "unit": "",
              "show_label": true
            }
          ]
        },
        {
          "title": "电阻法测量结果",
          "fields": [
            {
              "name": "start_room_temp",
              "type": "number",
              "description": "开始室温 t1（℃）",
              "unit": "℃"
            },
            {
              "name": "end_room_temp",
              "type": "number",
              "description": "结束时室温 t2（℃）",
              "unit": "℃"
            }
          ]
        },
        {
          "title": "电阻数值",
          "data_grid": true,
          "headers": [
            {
              "label": "冷态R1(Ω)"
            },
            {
              "label": "热态R2(Ω) 0.94倍"
            },
            {
              "label": "热态R2(Ω) 1倍"
            },
            {
              "label": "热态R2(Ω) 1.06倍"
            }
          ],
          "fields": [
            {
              "name": "stator_resistance",
              "type": "number_array",
              "description": "定子",
              "array_size": 4,
              "unit": "Ω"
            },
            {
              "name": "rotor_resistance",
              "type": "number_array",
              "description": "转子",
              "array_size": 4,
              "unit": "Ω"
            }
          ]
        },
        {
          "title": "温升数值",
          "data_grid": true,
          "headers": [
            {
              "label": "转子 0.94倍"
            },
            {
              "label": "转子 1倍"
            },
            {
              "label": "转子 1.06倍"
            },
            {
              "label": "定子 0.94倍"
            },
            {
              "label": "定子 1倍"
            },
            {
              "label": "定子 1.06倍"
            }
          ],
          "fields": [
            {
              "name": "temperature_rise",
              "type": "number_array",
              "description": "温升Δt（K）报告值",
              "array_size": 6,
              "unit": "K"
            },
            {
              "name": "temperature_rise_calc",
              "type": "number_array",
              "description": "温升Δt（K）计算值",
              "array_size": 6,
              "unit": "K",
              "computed": true
            }
          ]
        },
        {
          "title": "热电偶法测量结果",
          "data_grid": true,
          "headers": [
            {
              "label": "机壳"
            },
            {
              "label": "刷握"
            },
            {
              "label": "定子线圈出风口"
            },
            {
              "label": "定子线圈进风口"
            },
            {
              "label": "开关"
            },
            {
              "label": "电容"
            },
            {
              "label": "调速板"
            },
            {
              "label": "变压器"
            },
            {
              "label": "其他"
            }
          ],
          "fields": [
            {
              "name": "thermocouple_temperature",
              "type": "number_array",
              "description": "热态温度(℃)",
              "array_size": 9,
              "unit": "℃"
            }
          ]
        }
      ],
      "rules": [
        {
          "type": "formula_verify",
          "description": "转子温升 0.94倍",
          "formula": "(rotor_resistance_1 - rotor_resistance_0) / rotor_resistance_0 * (234.5 + start_room_temp) - (end_room_temp - start_room_temp)",
          "output_field": "temperature_rise_calc_0",
          "report_field": "temperature_rise_0",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "转子温升 1倍",
          "formula": "(rotor_resistance_2 - rotor_resistance_0) / rotor_resistance_0 * (234.5 + start_room_temp) - (end_room_temp - start_room_temp)",
          "output_field": "temperature_rise_calc_1",
          "report_field": "temperature_rise_1",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "转子温升 1.06倍",
          "formula": "(rotor_resistance_3 - rotor_resistance_0) / rotor_resistance_0 * (234.5 + start_room_temp) - (end_room_temp - start_room_temp)",
          "output_field": "temperature_rise_calc_2",
          "report_field": "temperature_rise_2",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "定子温升 0.94倍",
          "formula": "(stator_resistance_1 - stator_resistance_0) / stator_resistance_0 * (234.5 + start_room_temp) - (end_room_temp - start_room_temp)",
          "output_field": "temperature_rise_calc_3",
          "report_field": "temperature_rise_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "定子温升 1倍",
          "formula": "(stator_resistance_2 - stator_resistance_0) / stator_resistance_0 * (234.5 + start_room_temp) - (end_room_temp - start_room_temp)",
          "output_field": "temperature_rise_calc_4",
          "report_field": "temperature_rise_4",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "定子温升 1.06倍",
          "formula": "(stator_resistance_3 - stator_resistance_0) / stator_resistance_0 * (234.5 + start_room_temp) - (end_room_temp - start_room_temp)",
          "output_field": "temperature_rise_calc_5",
          "report_field": "temperature_rise_5",
          "tolerance_pct": 5
        },
        {
          "type": "limit",
          "description": "温升限值",
          "field": "temperature_rise",
          "operator": "<=",
          "value": 105
        }
      ]
    }
  },
  {
    "name": "clause25_power_cord_bending",
    "standard": "GB 3883.1-2014",
    "standard_dir": "GB3883",
    "title": "电缆弯曲测试",
    "description": "电缆、护套弯曲测试",
    "display": "电缆弯曲测试",
    "template": {
      "standard": "GB 3883.1-2014",
      "clause": "25",
      "title": "电缆弯曲测试",
      "description": "电缆、护套弯曲测试",
      "version": "1.1",
      "tables": [
        {
          "title": "提拉测试",
          "fields": [
            {
              "name": "pull_test_force",
              "type": "number",
              "description": "测试拉力(N)",
              "unit": "N"
            },
            {
              "name": "pull_test_torque",
              "type": "number",
              "description": "测试扭矩(N·m)",
              "unit": "N·m"
            },
            {
              "name": "pull_test_count",
              "type": "number",
              "description": "提拉次数",
              "unit": ""
            },
            {
              "name": "pull_test_result",
              "type": "text",
              "description": "测试结果",
              "unit": ""
            }
          ]
        },
        {
          "title": "弯曲测试",
          "fields": [
            {
              "name": "bend_item",
              "type": "text",
              "description": "弯曲项目",
              "unit": ""
            },
            {
              "name": "bend_handle",
              "type": "text",
              "description": "测试手柄",
              "unit": ""
            },
            {
              "name": "bend_cable_plate",
              "type": "text",
              "description": "电缆压板",
              "unit": ""
            },
            {
              "name": "bend_plate_dir",
              "type": "text",
              "description": "压板方向",
              "unit": ""
            },
            {
              "name": "bend_weight",
              "type": "number",
              "description": "悬挂重量",
              "unit": ""
            },
            {
              "name": "bend_count",
              "type": "number",
              "description": "弯曲次数",
              "unit": ""
            },
            {
              "name": "bend_wire_count",
              "type": "number",
              "description": "导线根数",
              "unit": ""
            },
            {
              "name": "bend_break_count",
              "type": "number",
              "description": "折断根数",
              "unit": ""
            },
            {
              "name": "bend_equipment",
              "type": "text",
              "description": "测试设备",
              "unit": ""
            },
            {
              "name": "bend_break_rate",
              "type": "number",
              "description": "折断率(%) 计算值",
              "unit": "%",
              "computed": true
            }
          ]
        },
        {
          "title": "曲率测试",
          "fields": [
            {
              "name": "curve_temp",
              "type": "number",
              "description": "环境温度(℃)",
              "unit": "℃"
            },
            {
              "name": "curve_weight",
              "type": "number",
              "description": "试物重量(Kg)",
              "unit": "Kg"
            },
            {
              "name": "curve_radius",
              "type": "number",
              "description": "曲率半径",
              "unit": ""
            },
            {
              "name": "curve_result",
              "type": "text",
              "description": "测试结果",
              "unit": ""
            }
          ]
        }
      ],
      "rules": [
        {
          "type": "formula_verify",
          "description": "导线折断率",
          "formula": "bend_break_count / bend_wire_count * 100",
          "output_field": "bend_break_rate",
          "tolerance_pct": 0
        },
        {
          "type": "limit",
          "description": "折断率限值(<10%)",
          "field": "bend_break_rate",
          "operator": "<",
          "value": 10
        }
      ]
    }
  },
  {
    "name": "gb4343_1_emission",
    "standard": "GB 4343.1-2018",
    "standard_dir": "GB4343",
    "title": "EMC",
    "description": "电磁兼容发射测试",
    "display": "EMC",
    "template": {
      "standard": "GB 4343.1-2018",
      "clause": "1",
      "title": "EMC",
      "description": "电磁兼容发射测试",
      "version": "1.2",
      "tables": [
        {
          "title": "测试数据及判定 - 准峰值Qp",
          "data_grid": true,
          "headers": [
            {
              "label": "频率点(MHz)"
            },
            {
              "label": "测量值(DBuV)"
            },
            {
              "label": "限制(DBuV)"
            },
            {
              "label": "余量(dB)"
            },
            {
              "label": "判定"
            }
          ],
          "fields": [
            {
              "name": "qp_row_1",
              "type": "number_array",
              "description": "准峰值行1",
              "array_size": 5
            },
            {
              "name": "qp_row_2",
              "type": "number_array",
              "description": "准峰值行2",
              "array_size": 5
            },
            {
              "name": "qp_row_3",
              "type": "number_array",
              "description": "准峰值行3",
              "array_size": 5
            },
            {
              "name": "qp_row_4",
              "type": "number_array",
              "description": "准峰值行4",
              "array_size": 5
            },
            {
              "name": "qp_row_5",
              "type": "number_array",
              "description": "准峰值行5",
              "array_size": 5
            },
            {
              "name": "qp_margin_calc",
              "type": "number_array",
              "description": "余量计算值(dB)",
              "array_size": 5,
              "unit": "dB",
              "computed": true
            }
          ]
        },
        {
          "title": "测试数据及判定 - 平均值AV",
          "data_grid": true,
          "headers": [
            {
              "label": "频率点(MHz)"
            },
            {
              "label": "测量值(DBuV)"
            },
            {
              "label": "限制(DBuV)"
            },
            {
              "label": "余量(dB)"
            },
            {
              "label": "判定"
            }
          ],
          "fields": [
            {
              "name": "av_row_1",
              "type": "number_array",
              "description": "平均值行1",
              "array_size": 5
            },
            {
              "name": "av_row_2",
              "type": "number_array",
              "description": "平均值行2",
              "array_size": 5
            },
            {
              "name": "av_row_3",
              "type": "number_array",
              "description": "平均值行3",
              "array_size": 5
            },
            {
              "name": "av_row_4",
              "type": "number_array",
              "description": "平均值行4",
              "array_size": 5
            },
            {
              "name": "av_row_5",
              "type": "number_array",
              "description": "平均值行5",
              "array_size": 5
            },
            {
              "name": "av_margin_calc",
              "type": "number_array",
              "description": "余量计算值(dB)",
              "array_size": 5,
              "unit": "dB",
              "computed": true
            }
          ]
        }
      ],
      "rules": [
        {
          "type": "formula_verify",
          "description": "Qp 行1 余量",
          "formula": "qp_row_1_1 - qp_row_1_2",
          "output_field": "qp_margin_calc_0",
          "report_field": "qp_row_1_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "Qp 行2 余量",
          "formula": "qp_row_2_1 - qp_row_2_2",
          "output_field": "qp_margin_calc_1",
          "report_field": "qp_row_2_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "Qp 行3 余量",
          "formula": "qp_row_3_1 - qp_row_3_2",
          "output_field": "qp_margin_calc_2",
          "report_field": "qp_row_3_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "Qp 行4 余量",
          "formula": "qp_row_4_1 - qp_row_4_2",
          "output_field": "qp_margin_calc_3",
          "report_field": "qp_row_4_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "Qp 行5 余量",
          "formula": "qp_row_5_1 - qp_row_5_2",
          "output_field": "qp_margin_calc_4",
          "report_field": "qp_row_5_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "AV 行1 余量",
          "formula": "av_row_1_1 - av_row_1_2",
          "output_field": "av_margin_calc_0",
          "report_field": "av_row_1_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "AV 行2 余量",
          "formula": "av_row_2_1 - av_row_2_2",
          "output_field": "av_margin_calc_1",
          "report_field": "av_row_2_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "AV 行3 余量",
          "formula": "av_row_3_1 - av_row_3_2",
          "output_field": "av_margin_calc_2",
          "report_field": "av_row_3_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "AV 行4 余量",
          "formula": "av_row_4_1 - av_row_4_2",
          "output_field": "av_margin_calc_3",
          "report_field": "av_row_4_3",
          "tolerance_pct": 5
        },
        {
          "type": "formula_verify",
          "description": "AV 行5 余量",
          "formula": "av_row_5_1 - av_row_5_2",
          "output_field": "av_margin_calc_4",
          "report_field": "av_row_5_3",
          "tolerance_pct": 5
        }
      ]
    }
  }
];

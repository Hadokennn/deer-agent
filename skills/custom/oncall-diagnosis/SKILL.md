---
name: oncall-diagnosis
description: 商品上品表单 Oncall 诊断流程知识
license: proprietary
allowed-tools: [bash, read_file, ask_clarification, task]
---

# 商品上品表单诊断知识

## 五元组说明（映射关系见 references/template_map.json）

| 字段 | 类型 | 说明 |
|------|------|------|
| category_id | int | 叶子类目 ID |
| product_type | int | 商品类型（团购/代金券/外卖...） |
| product_sub_type | int | 商品子类型（默认为空） |
| template_type | int | 模板类型，默认 1 |
| template_sub_type | int | 模板子类型，默认 0 |

## 代码仓库布局

```
/mnt/user-data/workspace/repos/
└── fe_ls_tobias_goods_mono/
  └── packages/components/src/goods/
      └── {ComponentName}/
          ├── PC.tsx       # PC端组件入口
          ├── APP.tsx       # 移动端组件入口
          ├── index.store.json  # 组件索引文件
          └── interface.ts    # 类型定义
```

## CLI 外化规范（防止 context rot）

**禁止**把整个文件读入 context。正确做法：

```bash
# 定位组件目录
rg -l "ComponentName" /mnt/user-data/workspace/goods-components/packages/ --type ts

# 只提取关键函数
rg -n "onFieldValueChange\|hidden" /mnt/user-data/workspace/goods-components/.../effects.ts | head -30

# 只读关键行段
read_file(path="...", start_line=45, end_line=67)
```

## x-reactions 表达式说明

```json
"x-reactions": {
  "dependencies": ["product_source"],
  "fulfill": {
    "state": {
      "hidden": "{{$deps[0] !== 'external'}}"  // deps[0] 不等于 external 时隐藏
    }
  }
}
```

## 诊断报告模板

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 诊断报告

【结论】字段存在但隐藏 / 字段不存在 / 模板不存在

【模板信息】
  类目路径：{category_path}
  商品类型：{product_type}

【字段信息】
  字段名称：{field_title}（{field_key}）
  所在组件：{component_name}

【根因分析】
  联动类型：静态 x-reactions / 动态 effects
  隐藏条件：当 {dependency_field} = {value} 时隐藏

【建议操作】
  {actionable_suggestion}

【置信度】高 / 中（需运行时验证）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

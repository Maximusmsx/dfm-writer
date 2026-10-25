# Delphi 5 / Delphi 7 目标格式

工具默认 Delphi 7。版本选择保存在各配置的 `DELPHI_VERSION` 参数中，取值 `7` 或 `5`，旧配置没有该参数时按 `7` 加载。

| 项目 | Delphi 7 | Delphi 5 |
|---|---|---|
| 中文“中文”的生成片段 | `#20013#25991` | `'中文'`，实际字节 `27 D6 D0 CE C4 27` |
| ASCII 文本 | 单引号包裹 | 单引号包裹 |
| SQL 内容单引号 | `#39` | `#39` |
| Tab | `#9` | `#9` |
| 连续片段 | 直接相邻 | 直接相邻 |
| 长行续接 | `+`，不增加源码换行 | `+`，不增加源码换行 |
| 分段上限 | 64 个 UTF-16 码元 | 64 个 GBK 字节，不拆开汉字 |
| 源码空行 | `''` | `''` |
| 字符串列表 | `Lines.Strings = (...)` | `Lines.Strings = (...)` |
| 文件编码 | 中文 ANSI/GBK，无 BOM；新生成片段为 ASCII | 中文 ANSI/GBK，无 BOM |
| 数字字符范围检查 | 0～65535 | 0～255 |

原始 SQL：

```sql
  RETURN '中文';
```

Delphi 7：

```pascal
    Lines.Strings = (
      '  RETURN '#39#20013#25991#39';')
```

Delphi 5（下面的中文在实际文件中按 GBK 保存）：

```pascal
    Lines.Strings = (
      '  RETURN '#39'中文'#39';')
```

两者不能直接当成同一格式：Delphi 5 的字符串解析不能用大于 255 的数字表示汉字。UTF-8 BOM、UTF-16 BOM 也不能作为这两个目标版本的输出方案。说明依据为 [DFM 转换工具作者的格式分类及版本说明](https://ht-deko.com/tech032.html)。

“选择 Delphi 5”只决定本次 Memo 的生成格式，不会将其他组件及属性整体从 Delphi 7 迁移为 Delphi 5。写入前检查整份生成结果中的字符转义，避免留下明显不符合 Delphi 5 的 Unicode 数字。原有第三方组件是否支持目标版本，不在此工具的转换范围内。

已提供验证层次：

1. 已知 GBK 字节及 Unicode 字符值的测试向量。
2. 不引用主程序编解码函数的独立字节解析器。
3. 两种目标格式分别写入测试文件并与在线数据库源码逐行回读比对。
4. 重新打包后的 exe 自检。
5. `compat/CompatProbe.dpr` 原生验证源码与调用两套 dcc32 的脚本。它使用 ObjectTextToBinary 和真实 TMemo，输出 ANSI 内容后与期望 GBK 字节比较。

本机未找到 Delphi 5/7 编译器，或 vcl50/rtl70 等对应运行库，故第 5 层原生运行尚未执行。不能将前四层校验等同于 Delphi IDE 实测。该边界不影响 exe 运行，工具本身不依赖 Delphi 安装。

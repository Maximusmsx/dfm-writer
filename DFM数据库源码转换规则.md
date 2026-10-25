# UfrmUpdate.dfm 数据库源码写入 TMemo 的规则与范式

**版本适用范围补充（2026-10-24）：下面由原文件归纳的 Unicode 数字转义规则针对 Delphi 7。Delphi 5 使用 ANSI 文本 DFM，中文不能直接套用该数字转义范式。现工具已增加目标版本选择，默认 7；选择 5 时用中文 GBK 引号文本、最多 64 个 GBK 字节分段，并保持无 BOM。两种格式共用列表括号、`#39`、`#9` 和 `+` 续行，但中文表示不同。详见 README 的 Delphi 5 规则。**

核验日期：2026-10-24。只读连接测试库，Oracle 11.2.0.4，数据库字符集 `ZHS16GBK`。

核验文件：薪酬系统源码中的 `UfrmUpdate.dfm`（客户代码，未随仓库发布）。

结论：除了中文字符转义，还存在字符串包裹、单引号转义、控制字符转义、字符串片段拼接、长行分段、TStrings 列表封装、换行表示转换、DDL 头补充和项目说明注释。当前 DFM 与当前数据库还存在空白及源码版本差异；后两者不能归纳成固定转换算法。

## 1. 数据库对象的定位规则

`_Spec`、`_Body` 是项目约定的 Memo 后缀，不是数据库对象名的一部分。数据库对象通过 NAME + TYPE 区分：

| TMemo 名称 | USER_SOURCE.NAME | USER_SOURCE.TYPE |
|---|---|---|
| PackXC_SERVICE_Spec | XC_SERVICE | PACKAGE |
| PackXC_SERVICE_Body | XC_SERVICE | PACKAGE BODY |
| PackTAX_UNTAX_Spec | TAX_UNTAX | PACKAGE |
| PackTAX_UNTAX_Body | TAX_UNTAX | PACKAGE BODY |
| FuncCalcAddValueTax | CALCADDVALUETAX | FUNCTION |
| FuncCalcTaxPrepare | CALCTAXPREPARE | FUNCTION |
| FuncGetErrorMsg | GETERRORMSG | FUNCTION |

建议输入范式：

```sql
SELECT LINE, TEXT
  FROM USER_SOURCE
 WHERE NAME = :object_name
   AND TYPE = :object_type
 ORDER BY LINE;
```

跨 schema 使用 ALL_SOURCE 并增加 OWNER 条件。按 LINE 排序，不把包头、包体混在一起。本次实际取回 7,480 行，逐对象检查行号连续。

## 2. 每一项转换规则

### 2.1 补上 CREATE OR REPLACE

`USER_SOURCE` 中的首行从 `PACKAGE`、`PACKAGE BODY`、`FUNCTION` 等开始；Memo 中存的是可以直接提交执行的 DDL，因此前面有 `CREATE OR REPLACE `。

```text
PACKAGE XC_SERVICE AS
→ CREATE OR REPLACE PACKAGE XC_SERVICE AS

PACKAGE BODY TAX_UNTAX IS
→ CREATE OR REPLACE PACKAGE BODY TAX_UNTAX IS

FUNCTION CALCADDVALUETAX (
→ CREATE OR REPLACE FUNCTION CALCADDVALUETAX (
```

对本次 USER_SOURCE 输入，只给第一行补这个前缀。如果工具以后接受完整 CREATE DDL，则检查已有前缀，避免重复补充。不要把正文中的 FUNCTION、PROCEDURE、PACKAGE 全局替换。

### 2.2 前面增加一行项目说明注释

7 个 Memo 均比对象声明多出一行说明。按现文件逐字复现时，使用下面的映射，不推测统一模板：

| Memo | 解码后的首行 |
|---|---|
| PackXC_SERVICE_Spec | `/*包PACKAGE XC_SERVICE*/` |
| PackXC_SERVICE_Body | `/*包XC_SERVICE BODY*/` |
| PackTAX_UNTAX_Spec | `/*包PACKAGE TAX_UNTAX*/` |
| PackTAX_UNTAX_Body | `/*包PACKAGE BODY TAX_UNTAX*/` |
| FuncCalcAddValueTax | `/*CalcAddValueTax函数源码：*/` |
| FuncCalcTaxPrepare | `/* CalcTaxPrepare函数源码*/` |
| FuncGetErrorMsg | `/*GetErrorMsg函数源码：*/` |

这些注释存在于 Memo 中，不存在于对应 USER_SOURCE 开头；它们是项目内容约定，并非 DFM 语法要求。

### 2.3 普通可打印 ASCII 文本用单引号包裹

连续的普通 ASCII 字符写成一个字符串片段：

```text
BEGIN
→ 'BEGIN'

  RETURN 0;
→ '  RETURN 0;'
```

引号内部的前导空格属于 SQL 源码，必须保留。引号外部的缩进属于 DFM 排版。

建议本文件的编码判定：字符值为 32～126 且不是 ASCII 单引号 39，进入普通文本片段；其他字符进入 `#十进制数` 片段。

### 2.4 中文及其他非 ASCII 字符写成 #十进制字符值

```text
中文
→ #20013#25991

/*中文*/
→ '/*'#20013#25991'*/'
```

不只是汉字：全角标点、弯引号和其他非 ASCII 符号也遵循这一规则。本次 7 个 Memo 中实际出现 `#8220`、`#8221`、`#8216`、`#164` 等。

注意：这里是字符值，不是 UTF-8 字节值，也不是 GBK 双字节分别转成十进制。数据库查询返回的文本应先正确解码，再逐字符序列化。本次数据库字符集为 ZHS16GBK。

Delphi 7 的标准 TMemo/string 属于 ANSI 环境；DFM 的数字字符表示不意味着运行时可无条件无损保存任意 Unicode。当前文件中的实际字符已完成本次解码比对；超出目标代码页的字符未做 Delphi 7 加载验证。

### 2.5 SQL 内部的单引号写成 #39

这是中文以外最关键的转义。当前 7 个 Memo 的实际形式是 `#39`，没有发现把内容单引号写成带引号片段内部双写引号的形式。

```text
  RETURN 'T';
→ '  RETURN '#39'T'#39';'

  RETURN '';
→ '  RETURN '#39#39';'
```

如果 SQL 原来含两个连续单引号，则逐字变成两个 `#39`。不要先做一遍 SQL 单引号加倍再做 DFM 转义，否则会改变 SQL 内容。

### 2.6 Tab 等控制字符用数字字符片段

当前这 7 个 Memo 中，XC_SERVICE 包体实际保留了 1 个 Tab，对应 DFM 的 `#9`。它不是自动扩展成若干空格。

```text
[Tab]SELECT ...
→ #9'SELECT ...'
```

通用编码函数可将控制字符统一编码为 `#字符值`；本次实际样本证明了 Tab，未在这 7 个 Memo 中发现内嵌 `#13`、`#10` 的源码换行写法。

### 2.7 同一个字符串内部，不同片段直接相邻拼接

```text
'  RETURN '#39#20013#25991#39';'
```

这是一个字符串项，解码为：

```sql
  RETURN '中文';
```

`'文本'` 和 `#数字` 之间不需要逗号，也不需要 `+`。非 ASCII 片段后如果还跟普通文本，就重新打开单引号片段。

### 2.8 长源码行通常先按 64 个解码字符切片，再转义

本文件的主流范式：以原字符串的字符数量计数，每段 64 个字符；不是按转义后的 DFM 文本长度计数，不是按 GBK 字节数计数，也不是在 SQL 词边界切分。

```text
      
        '第一段的编码结果' +
        '第二段的编码结果'
```

`+` 连接的仍然是同一个 Lines.Strings 项，不会给 SQL 增加换行、空格或加号。切分可以发生在标识符中间，复原时直接连接即可。

实测：7 个 Memo 合计有 1,727 个续行 `+`，其中 1,726 个前面的片段解码长度为 64；另 1 个为 116。

按“64 字符切片 + 本文字符编码”重新生成后，对 7,474 个 Memo 逻辑行进行词法比较，7,471 行完全一致。仅 XC_SERVICE 包体的 3 行分段布局不一致，对应原 DFM 行 21304、21381～21382、21479。这三行的解码内容仍可以无损重建。

因此，64 是本文件可采用的输出范式，不应把它当作 DFM 接受字符串的绝对长度限制。三处例外的形成原因仅凭当前文件无法确定。

### 2.9 每个 SQL 源码行对应 Lines.Strings 的一个字符串项

实际写入目标是 TMemo 的 `Lines.Strings`：

```pascal
    Lines.Strings = (
      'CREATE OR REPLACE ...'
      'BEGIN'
      '  RETURN 0;'
      'END;')
```

各项之间不加逗号、不加分号。SQL 原有分号保留在字符串里面。列表括号是 DFM 语法，不是 SQL 内容。

空字符串列表项表示一个真正的空行：

```pascal
      ''
```

只有空格的源码行必须保留其空格，例如 `'  '`，不能随意变成 `''`。

### 2.10 源码换行变成列表项边界；DFM 自身使用 CRLF

USER_SOURCE.TEXT 中每行自带的末尾换行属于源行分隔。生成字符串项时去掉该行分隔符，不能把这个换行再作为 `#10` 写进项里，否则恢复 Memo 文本时会多出换行。

同时保留实际的空行项，不能对整段源码执行无差别 `strip()`、过滤空行或把每行都 `Trim()`。

本次原 DFM 为 1,564,402 字节，全文只有 ASCII 字节，没有 BOM，30,154 个换行全部为 CRLF，无单独 LF。因此工具可保持“ASCII 文本 + CRLF + 无 BOM”的输出范式。编码后的数字转义也是普通 ASCII 文本，文件本身并不是 UTF-16。

`TMemo.Text` 恢复文本时由 Windows/VCL 行列表机制组织换行；本次没有启动 Delphi 7 实测最后一行后是否附带终止换行。工具的内容核对宜以 Lines 项序列为准，单独定义文本末尾换行策略。

### 2.11 保留终结分号，不附加 SQL*Plus 执行包装

7 个 Memo 的 PL/SQL 均保留原来的结尾 `END;` 或 `END 名称;`，没有单独的 `/` 执行行，也没有 `SHOW ERRORS`、`SET DEFINE`、`PROMPT` 等脚本命令。

同目录 UfrmUpdate.pas 中，函数使用 `Memo.Text → UpdateFuncProc → ExecSingleSql`，包使用 `Memo.Text → UpdatePackage → ExecSingleSql`，随后调用 `ExecSQL`。这与存储可直接提交的 DDL 形式一致。

输入若直接来自 USER_SOURCE，不需要增加上述脚本包装。不要删除 SQL 正文中的 `/`、注释符号、运算符或分号。

### 2.12 SQL 其他内容按原字符保留，不增加第二层转义

SQL 的 `||`、括号、双引号、反斜线、注释、`--`、`/* */` 等保持原样，只经过上述字符串编码。SQL 原有 `+` 是引号内的字符；DFM 续行 `+` 是引号外的语法，必须区分。

源码中如果出现字面文本 `#39`，应写成引号内的 `'#39'`，不能把它误当作要解码的 DFM 转义。编码应逐个原始字符执行，不要多轮正则替换已经生成的结果。

本次 7 个对象中没有 `@@@@`、`#YEAR#`、`#USER#`、`#NOWYEAR#`、`#TAX_CENTER#`，因此没有证据支持导出时要做年份、用户名或 schema 占位符改写。UfrmUpdate.pas 的包执行入口确有 `@@@@` 替换，但不是这 7 个对象的实际转换步骤。

## 3. 当前文件中存在、但不能做成通用转换规则的差异

| Memo | 数据库行数 | Memo 逻辑行数 | 解码后比较 |
|---|---:|---:|---|
| PackXC_SERVICE_Spec | 265 | 266 | 仅多出说明注释、CREATE OR REPLACE；其他内容逐行一致 |
| PackXC_SERVICE_Body | 5014 | 5037 | 另有源码内容差异 |
| PackTAX_UNTAX_Spec | 41 | 37 | DFM 缺少当前数据库的空方案常量及相关注释 |
| PackTAX_UNTAX_Body | 651 | 643 | DFM 缺少当前数据库按证件类型补选方案的分支 |
| FuncCalcAddValueTax | 303 | 291 | 空方案过滤、兜底逻辑不同，并有空白差异 |
| FuncCalcTaxPrepare | 988 | 985 | 月份检查、增值税入口条件、异常处理不同，并有空白差异 |
| FuncGetErrorMsg | 218 | 215 | DFM 缺少 -60000007 错误信息分支，并有空白差异 |

具体例子：

- XC_SERVICE 包体：变量 VARCHAR2(1000)/VARCHAR2(100)、日期 NULL 处理、REWARD_REC 记录声明、税率查询方式、部分字段赋值和动态 SQL 绑定写法不同。完整差异保留在本地 `evidence/` 中，未随仓库发布。
- CalcTaxPrepare：数据库末尾为生效的 `EXCEPTION / WHEN OTHERS / RETURN -10000000`，DFM 中是对应三行前加 `--` 的形式。序列化本身不会把程序注释掉。
- 空白：有些行在数据库中为空行，在 DFM 解码后为只含空格的行；部分行有不同的尾随空格；CalcAddValueTax、TAX_UNTAX 包体 Memo 最后还有空字符串项。没有统一的 Trim/加空行/删空行规律。
- 大小写与排版：数据库的函数声明为大写名称并在 `(` 前有空格，部分 Memo 声明用混合大小写且无该空格；其他对象又保留大写和空格。不能总结为必须统一大写或统一去空格。

这里只证明当前两个文本之间存在内容差异，不推断具体是谁在什么时间编辑、也不把差异当成转换时应删改的业务规则。转换工具应保存选定数据库版本的完整内容。

## 4. 可直接给后续工具开发使用的流程范式

```text
1. 根据映射确定 Memo 名称、数据库 NAME、TYPE。
2. 按 LINE 读取 USER_SOURCE，得到有序源行。
3. 去掉各源行的行分隔符，保留源码空格、空行和原有标点。
4. 仅在第一条对象声明前补 CREATE OR REPLACE。
5. 若需延续现文件风格，按映射在最前面加入说明注释。
6. 对每一个逻辑行：
   a. 空字符串生成 ''。
   b. 非空字符串先按 64 个字符分段。
   c. 每段内合并普通 ASCII 文本为 '文本'。
   d. 单引号、非 ASCII、控制字符逐个生成 #十进制值。
   e. 同段各片段直接相邻；跨段用 + 和 DFM 物理换行连接。
7. 所有逻辑行放入 Lines.Strings = (...) 列表。
8. 按现文件 CRLF、ASCII、无 BOM 的格式保存。
9. 只替换指定 Memo 的 Lines.Strings 值，保留其他控件和属性。
10. 重新解析生成结果，断言逻辑行序列与第 5 步输入逐字符一致。
```

转换正确性的判定式：

```text
DecodeDFM(EncodeDFM(DDL_lines)) == DDL_lines
```

64 字符分段属于输出布局；改变分段位置不能改变解码结果。转换工具不应为了逐字匹配旧 DFM 而丢掉数据库里新增的业务代码。

## 5. 核验材料与验证边界

本次核验使用的原始 DFM、在线源码快照和逐行差异保留在本地 `evidence/`，因包含客户业务代码，未随仓库发布。可公开的打包与格式报告见 `docs/validation/`。

- `analyze_dfm.py`：本次解码、编码往返验证与源码比对脚本；不改动原文件。需通过参数或 `DFM_SAMPLE` 指定本地 DFM。
- `evidence/db_source_hex.json`：本次在线 USER_SOURCE 取回结果，按数据库 GBK 字节十六进制保存，避免 CSV 内部逗号、引号、换行干扰文本内容。
- `evidence/*.db.sql`：数据库源码解码快照。
- `evidence/*.memo.sql`：DFM Lines.Strings 解码后的源码。
- `evidence/*.diff.txt`：逐行完整差异。
- `evidence/summary.json`：统计、非标准分段位置和去除行首尾空白/空行后的辅助差异。判断原文精确差异请以 diff 文件为准。

本次对数据库 7,480 行和 Memo 7,474 行均执行了编码→解码逐字符相等断言，全部通过；另包含单引号、中文、Tab、空字符串、仅空格、加号、字面 #39、反斜线的边界样例。此验证是独立脚本的格式与内容往返校验，不等同于 Delphi 7 编译器/DFM 加载器验收。本次未改原 DFM/PAS，未执行数据库 DDL 或业务过程，未启动 Delphi 7。

原 DFM SHA-256（本地样本）：`0df5b1ab6cdd94a745e77c9050a581a622b77e8b5cd8054c12d83dcc25705e14`。

官方背景参考：[Embarcadero ObjectBinaryToText](https://docwiki.embarcadero.com/Libraries/Florence/en/System.Classes.ObjectBinaryToText) 说明组件的二进制表示与文本表示的转换。本文关于 64 字符分段、项目注释、当前对象差异等结论以本次本地文件及在线数据库实测为依据，不将新版文档当作 Delphi 7 加载验证。

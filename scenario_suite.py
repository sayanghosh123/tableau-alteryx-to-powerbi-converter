"""Synthetic scenario catalog for migration proof testing.

The scenarios are intentionally generic and deterministic. They are designed to
exercise converter behavior and confidence reporting, not to prove business
parity with any real Tableau workbook or Alteryx workflow.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TableauFormula:
    caption: str
    formula: str
    role: str = "measure"
    datatype: str = "real"


@dataclass(frozen=True)
class TableauScenario:
    scenario_id: str
    name: str
    purpose: str
    formulas: tuple[TableauFormula, ...]
    expected_tokens: tuple[str, ...]
    confidence: str
    review_focus: str


@dataclass(frozen=True)
class AlteryxScenario:
    scenario_id: str
    name: str
    purpose: str
    tools: tuple[dict, ...]
    expected_tokens: tuple[str, ...]
    confidence: str
    review_focus: str


TABLEAU_SCENARIOS: tuple[TableauScenario, ...] = (
    TableauScenario(
        "TBL-01",
        "Aggregate arithmetic",
        "Basic measure arithmetic and ratio conversion.",
        (
            TableauFormula("Gross Profit", "SUM([sales_amount]) - SUM([cost_amount])"),
            TableauFormula("Margin Rate", "SUM([profit_amount]) / SUM([sales_amount])"),
        ),
        ("SUM('Sales'[sales_amount])", "DIVIDE("),
        "High",
        "Check numeric formatting and divide-by-zero behavior.",
    ),
    TableauScenario(
        "TBL-02",
        "Single-dimension fixed LOD",
        "Fixed-grain aggregation by one dimension.",
        (TableauFormula("Category Revenue", "{ FIXED [category] : SUM([sales_amount]) }"),),
        ("ALLEXCEPT", "'Sales'[category]"),
        "High",
        "Validate DAX filter context against Tableau LOD behavior.",
    ),
    TableauScenario(
        "TBL-03",
        "Multi-dimension fixed LOD",
        "Fixed-grain aggregation by two dimensions.",
        (TableauFormula("Region Segment Average", "{ FIXED [region], [segment] : AVG([order_value]) }"),),
        ("ALLEXCEPT", "'Sales'[region]", "'Sales'[segment]"),
        "High",
        "Validate all grain columns are retained.",
    ),
    TableauScenario(
        "TBL-04",
        "Running total",
        "Cumulative date-based table calculation.",
        (TableauFormula("Running Sales", "RUNNING_SUM(SUM([sales_amount]))"),),
        ("ALLSELECTED", "'Date'[Date]"),
        "High",
        "Confirm date table and visual grain.",
    ),
    TableauScenario(
        "TBL-05",
        "Percent of total",
        "Table total translated to DAX denominator.",
        (TableauFormula("Share of Sales", "SUM([sales_amount]) / TOTAL(SUM([sales_amount]))"),),
        ("DIVIDE(", "ALL('Sales')"),
        "High",
        "Confirm whether total should respect slicers.",
    ),
    TableauScenario(
        "TBL-06",
        "IF banding",
        "Conditional banding with ELSEIF.",
        (
            TableauFormula(
                "Margin Band",
                "IF [profit_margin] >= 0.3 THEN 'High' ELSEIF [profit_margin] >= 0.15 THEN 'Medium' ELSE 'Low' END",
                role="dimension",
                datatype="string",
            ),
        ),
        ("IF('Sales'[profit_margin]", '"High"'),
        "High",
        "Review calculated-column versus measure placement.",
    ),
    TableauScenario(
        "TBL-07",
        "CASE grouping",
        "Simple CASE expression over a dimension.",
        (
            TableauFormula(
                "Channel Group",
                "CASE [channel] WHEN 'Web' THEN 'Digital' WHEN 'App' THEN 'Digital' ELSE 'Assisted' END",
                role="dimension",
                datatype="string",
            ),
        ),
        ("SWITCH('Sales'[channel]", '"Digital"'),
        "Medium",
        "Check string matching and default bucket.",
    ),
    TableauScenario(
        "TBL-08",
        "Prior period lookup",
        "Offset table calculation scaffold.",
        (TableauFormula("Prior Period Sales", "LOOKUP(SUM([sales_amount]), -1)"),),
        ("DATEADD", "-1"),
        "Medium",
        "Confirm date offset unit and sort direction.",
    ),
    TableauScenario(
        "TBL-09",
        "INCLUDE LOD",
        "Additional-grain LOD expression.",
        (TableauFormula("Include Order Grain", "{ INCLUDE [order_id] : SUM([sales_amount]) }"),),
        ("VALUES('Sales'[order_id])", "CALCULATE"),
        "Medium",
        "Validate visual grain before production use.",
    ),
    TableauScenario(
        "TBL-10",
        "EXCLUDE LOD",
        "Remove a grain column from filter context.",
        (TableauFormula("Exclude Region Sales", "{ EXCLUDE [region] : SUM([sales_amount]) }"),),
        ("REMOVEFILTERS('Sales'[region])", "CALCULATE"),
        "Medium",
        "Validate context-removal behavior.",
    ),
    TableauScenario(
        "TBL-11",
        "Date differences",
        "Multiple date granularities.",
        (
            TableauFormula("Weeks Since Order", "DATEDIFF('week', [order_date], TODAY())"),
            TableauFormula("Quarters Since Order", "DATEDIFF('quarter', [order_date], TODAY())"),
        ),
        ("DATEDIFF('Sales'[order_date], TODAY(), WEEK)", "QUARTER"),
        "High",
        "Confirm date type and timezone assumptions.",
    ),
    TableauScenario(
        "TBL-12",
        "Null handling",
        "Null-to-zero and fallback conversions.",
        (
            TableauFormula("Safe Discount", "ZN([discount_amount])"),
            TableauFormula("Safe Refund", "IFNULL([refund_amount], 0)"),
            TableauFormula("Safe Sales", "ZN(SUM([sales_amount]))"),
        ),
        ("COALESCE('Sales'[discount_amount], 0)", "COALESCE('Sales'[refund_amount], 0)", "COALESCE(SUM('Sales'[sales_amount]), 0)"),
        "High",
        "Confirm fallback values are still valid.",
    ),
    TableauScenario(
        "TBL-13",
        "String functions",
        "String extraction and contains checks.",
        (
            TableauFormula("SKU Prefix", "LEFT([sku], 3)", role="dimension", datatype="string"),
            TableauFormula("Flagged Note", "CONTAINS([notes], 'urgent')", role="dimension", datatype="boolean"),
        ),
        ("LEFT('Sales'[sku], 3)", "CONTAINSSTRING"),
        "Medium",
        "Review case sensitivity expectations.",
    ),
    TableauScenario(
        "TBL-14",
        "Ranking",
        "Rank table calculation scaffold.",
        (TableauFormula("Revenue Rank", "RANK(SUM([sales_amount]))"),),
        ("RANKX", "ALL('Sales')"),
        "Medium",
        "Confirm ranking partition and tie behavior.",
    ),
    TableauScenario(
        "TBL-15",
        "Moving average",
        "Window average scaffold.",
        (TableauFormula("Seven Day Average", "WINDOW_AVG(SUM([sales_amount]), -6, 0)"),),
        ("AVERAGEX", "DATESINPERIOD"),
        "Medium",
        "Confirm window length and date grain.",
    ),
    TableauScenario(
        "TBL-16",
        "Distinct and range aggregates",
        "COUNTD, MIN, MAX, and AVG mappings.",
        (
            TableauFormula("Distinct Orders", "COUNTD([order_id])"),
            TableauFormula("Average Quantity", "AVG([quantity])"),
            TableauFormula("Latest Order", "MAX([order_date])"),
        ),
        ("DISTINCTCOUNT", "AVERAGE", "MAX"),
        "High",
        "Confirm aggregate data types.",
    ),
    TableauScenario(
        "TBL-17",
        "Boolean thresholds",
        "AND/OR conditional expression.",
        (
            TableauFormula(
                "Priority Flag",
                "IF [sales_amount] > 1000 AND [profit_margin] < 0.1 THEN 'Review' ELSE 'OK' END",
                role="dimension",
                datatype="string",
            ),
        ),
        ("&&", '"Review"'),
        "High",
        "Confirm threshold values.",
    ),
    TableauScenario(
        "TBL-18",
        "Window sum",
        "Rolling-window sum scaffold.",
        (TableauFormula("Seven Day Sum", "WINDOW_SUM(SUM([sales_amount]), -6, 0)"),),
        ("SUMX", "DATESINPERIOD"),
        "Medium",
        "Confirm window bounds and partitioning.",
    ),
    TableauScenario(
        "TBL-19",
        "Total only",
        "Standalone table total.",
        (TableauFormula("All Sales", "TOTAL(SUM([sales_amount]))"),),
        ("CALCULATE", "ALL('Sales')"),
        "High",
        "Confirm total scope.",
    ),
    TableauScenario(
        "TBL-20",
        "Mixed calculations",
        "A compact report with LOD, ratio, date, and banding formulas.",
        (
            TableauFormula("Regional Baseline", "{ FIXED [region] : SUM([sales_amount]) }"),
            TableauFormula("Return Rate", "SUM([return_amount]) / SUM([sales_amount])"),
            TableauFormula("Months Since Order", "DATEDIFF('month', [order_date], TODAY())"),
        ),
        ("ALLEXCEPT", "DIVIDE", "MONTH"),
        "High",
        "Review formula interactions across visuals.",
    ),
)


ALteryx_BASE_INPUT = {"type": "Input", "name": "Read source CSV"}
ALteryx_BASE_OUTPUT = {"type": "Output", "name": "Publish draft output"}


ALTERYX_SCENARIOS: tuple[AlteryxScenario, ...] = (
    AlteryxScenario(
        "ALX-01",
        "Linear cleanse aggregate",
        "Input, filter, formula, summarize, sort, output.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Filter", "name": "Keep positive sales", "expression": "[sales_amount] > 0"},
            {"type": "Formula", "name": "Add profit", "formulas": [("profit_amount", "[sales_amount] - [cost_amount]")]},
            {"type": "Summarize", "name": "Summarize by region", "group_by": ["region"], "aggregations": [("sales_amount", "Sum", "total_sales")]},
            {"type": "Sort", "name": "Sort total sales", "sort": [("total_sales", "Descending")]},
            ALteryx_BASE_OUTPUT,
        ),
        ("Table.SelectRows", "Table.Group", "Table.Sort"),
        "High",
        "Source binding and aggregate parity.",
    ),
    AlteryxScenario(
        "ALX-02",
        "Nested null cleanup",
        "Nested conditionals and empty checks.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Formula", "name": "Default missing values", "formulas": [("clean_status", 'IIF(IsEmpty([status]), "Unknown", [status])'), ("safe_sales", "IIF(IsNull([sales_amount]), 0, [sales_amount])")]},
            ALteryx_BASE_OUTPUT,
        ),
        ("if", "Text.Length", "safe_sales"),
        "Medium",
        "Confirm nested conditional behavior.",
    ),
    AlteryxScenario(
        "ALX-03",
        "Select field subset",
        "Projection and missing-field tolerance.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Select", "name": "Keep reporting fields", "fields": ["order_id", "region", "sales_amount"]},
            ALteryx_BASE_OUTPUT,
        ),
        ("Table.SelectColumns", "MissingField.Ignore"),
        "High",
        "Confirm rename/type metadata outside this scaffold.",
    ),
    AlteryxScenario(
        "ALX-04",
        "Inner join scaffold",
        "Join key parsing with review flag.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Join", "name": "Join product lookup", "left_key": "product_id", "right_key": "product_id", "join_type": "Inner"},
            ALteryx_BASE_OUTPUT,
        ),
        ("Table.NestedJoin", "JoinKind.Inner"),
        "Medium",
        "Wire left and right branches manually.",
    ),
    AlteryxScenario(
        "ALX-05",
        "Full outer reconciliation",
        "Full outer join scaffold.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Join", "name": "Reconcile two extracts", "left_key": "order_id", "right_key": "order_id", "join_type": "FullOuter"},
            ALteryx_BASE_OUTPUT,
        ),
        ("JoinKind.FullOuter", "Table.NestedJoin"),
        "Medium",
        "Review null handling after reconciliation.",
    ),
    AlteryxScenario(
        "ALX-06",
        "Union scaffold",
        "Union tool creates combine scaffold.",
        (ALteryx_BASE_INPUT, {"type": "Union", "name": "Combine extracts"}, ALteryx_BASE_OUTPUT),
        ("Table.Combine",),
        "Medium",
        "Add all source branches and align schemas.",
    ),
    AlteryxScenario(
        "ALX-07",
        "Running total after sort",
        "Sort plus Multi-Row Formula running total.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Sort", "name": "Sort by date", "sort": [("order_date", "Ascending")]},
            {"type": "MultiRowFormula", "name": "Running sales", "formulas": [("running_sales", "[Row-1:running_sales] + [sales_amount]")]},
            ALteryx_BASE_OUTPUT,
        ),
        ("Table.AddIndexColumn", "List.FirstN"),
        "Medium",
        "Confirm ordering and grouping reset rules.",
    ),
    AlteryxScenario(
        "ALX-08",
        "Prior row delta",
        "Lag-style Multi-Row Formula flagged for review.",
        (
            ALteryx_BASE_INPUT,
            {"type": "MultiRowFormula", "name": "Prior row delta", "formulas": [("sales_delta", "[sales_amount] - [Row-1:sales_amount]")]},
            ALteryx_BASE_OUTPUT,
        ),
        ("Table.AddIndexColumn", "sales_delta"),
        "Medium",
        "Generated scaffold needs manual semantic review.",
    ),
    AlteryxScenario(
        "ALX-09",
        "Multi-key sort",
        "Sort with multiple fields and directions.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Sort", "name": "Sort region and date", "sort": [("region", "Ascending"), ("order_date", "Descending"), ("sales_amount", "Descending")]},
            ALteryx_BASE_OUTPUT,
        ),
        ("Order.Ascending", "Order.Descending"),
        "High",
        "Confirm sorted order before downstream row logic.",
    ),
    AlteryxScenario(
        "ALX-10",
        "Multi-aggregate summarize",
        "Group by two fields with mixed aggregate actions.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Summarize", "name": "Summarize region category", "group_by": ["region", "category"], "aggregations": [("sales_amount", "Sum", "total_sales"), ("profit_margin", "Avg", "avg_margin"), ("order_id", "Count", "order_count"), ("order_date", "Max", "latest_order")]},
            ALteryx_BASE_OUTPUT,
        ),
        ("List.Average", "Table.RowCount", "List.Max"),
        "High",
        "Confirm aggregate action semantics.",
    ),
    AlteryxScenario(
        "ALX-11",
        "Advanced summarize actions",
        "Distinct count, first, last, and concatenate.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Summarize", "name": "Summarize advanced actions", "group_by": ["region"], "aggregations": [("order_id", "CountDistinct", "distinct_orders"), ("category", "First", "first_category"), ("category", "Last", "last_category"), ("sku", "Concatenate", "sku_list")]},
            ALteryx_BASE_OUTPUT,
        ),
        ("List.Distinct", "List.First", "Text.Combine"),
        "Medium",
        "Confirm ordering for first/last outputs.",
    ),
    AlteryxScenario(
        "ALX-12",
        "Date window filter",
        "DateTimeToday expression in a filter.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Filter", "name": "Recent open orders", "expression": '[order_date] >= DateTimeToday() - 30 AND [status] != "Closed"'},
            ALteryx_BASE_OUTPUT,
        ),
        ("Date.From(DateTime.LocalNow())", "<>"),
        "Medium",
        "Confirm date arithmetic against source types.",
    ),
    AlteryxScenario(
        "ALX-13",
        "Text normalization",
        "Trim, casing, and casting formulas.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Formula", "name": "Normalize text fields", "formulas": [("sku_clean", "Uppercase(Trim([sku]))"), ("region_lower", "Lowercase([region])"), ("sales_text", "ToString([sales_amount])"), ("quantity_number", "ToNumber([quantity])")]},
            ALteryx_BASE_OUTPUT,
        ),
        ("Text.Upper", "Text.Trim", "Number.From"),
        "High",
        "Confirm locale-specific number parsing.",
    ),
    AlteryxScenario(
        "ALX-14",
        "Chained formulas",
        "Later formulas reference earlier generated columns.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Formula", "name": "Chained calculations", "formulas": [("gross_profit", "[sales_amount] - [cost_amount]"), ("profit_rate", "[gross_profit] / [sales_amount]"), ("profit_label", 'IIF([profit_rate] > 0.2, "Strong", "Review")')]},
            ALteryx_BASE_OUTPUT,
        ),
        ("List.Accumulate", "profit_rate", "profit_label"),
        "Medium",
        "Confirm sequential dependency behavior.",
    ),
    AlteryxScenario(
        "ALX-15",
        "Unique rows",
        "Distinct rows by one or more keys.",
        (ALteryx_BASE_INPUT, {"type": "Unique", "name": "Deduplicate orders", "fields": ["order_id"]}, ALteryx_BASE_OUTPUT),
        ("Table.Distinct", "order_id"),
        "High",
        "Confirm which duplicate record should survive.",
    ),
    AlteryxScenario(
        "ALX-16",
        "Sample rows",
        "Top-N sampling scaffold.",
        (ALteryx_BASE_INPUT, {"type": "Sample", "name": "Take first rows", "count": "25"}, ALteryx_BASE_OUTPUT),
        ("Table.FirstN", "25"),
        "High",
        "Confirm sampling method and ordering.",
    ),
    AlteryxScenario(
        "ALX-17",
        "Record ID",
        "Add sequential identifier.",
        (ALteryx_BASE_INPUT, {"type": "RecordID", "name": "Add row id", "field": "row_id", "start": "1"}, ALteryx_BASE_OUTPUT),
        ("Table.AddIndexColumn", "row_id"),
        "High",
        "Confirm start value and ordering.",
    ),
    AlteryxScenario(
        "ALX-18",
        "Text to columns",
        "Split delimited text into fields.",
        (
            ALteryx_BASE_INPUT,
            {"type": "TextToColumns", "name": "Split compound key", "field": "compound_key", "delimiter": "|", "columns": ["region_code", "category_code"]},
            ALteryx_BASE_OUTPUT,
        ),
        ("Table.SplitColumn", "Splitter.SplitTextByDelimiter"),
        "High",
        "Confirm delimiter and overflow handling.",
    ),
    AlteryxScenario(
        "ALX-19",
        "Transpose and crosstab",
        "Unpivot then pivot scaffold.",
        (
            ALteryx_BASE_INPUT,
            {"type": "Transpose", "name": "Unpivot metric columns", "key_fields": ["order_id", "region"]},
            {"type": "CrossTab", "name": "Pivot categories", "group": "region", "header": "category", "value": "sales_amount"},
            ALteryx_BASE_OUTPUT,
        ),
        ("Table.UnpivotOtherColumns", "Table.Pivot"),
        "Medium",
        "Confirm grain and aggregation.",
    ),
    AlteryxScenario(
        "ALX-20",
        "Mixed preparation flow",
        "Cleansing, regex, date parsing, append scaffold, select, output.",
        (
            ALteryx_BASE_INPUT,
            {"type": "DataCleansing", "name": "Clean text", "fields": ["sku", "category"]},
            {"type": "Regex", "name": "Extract code", "field": "sku", "output": "sku_code", "pattern": "([A-Z]+)-.*"},
            {"type": "DateTime", "name": "Parse order date", "field": "order_date", "output": "order_date"},
            {"type": "AppendFields", "name": "Append lookup fields"},
            {"type": "Select", "name": "Final shape", "fields": ["order_id", "region", "sku_code", "order_date"]},
            ALteryx_BASE_OUTPUT,
        ),
        ("Table.TransformColumns", "Power Query M has no built-in regex replacement", "Date.FromText", "Table.SelectColumns"),
        "Medium",
        "Regex and append fields require review.",
    ),
)


def write_tableau_scenario(scenario: TableauScenario, path: Path) -> None:
    columns = [
        _tableau_column("sales_amount", "real", "measure"),
        _tableau_column("cost_amount", "real", "measure"),
        _tableau_column("profit_amount", "real", "measure"),
        _tableau_column("return_amount", "real", "measure"),
        _tableau_column("order_value", "real", "measure"),
        _tableau_column("profit_margin", "real", "measure"),
        _tableau_column("quantity", "integer", "measure"),
        _tableau_column("discount_amount", "real", "measure"),
        _tableau_column("refund_amount", "real", "measure"),
        _tableau_column("order_id", "string", "dimension"),
        _tableau_column("region", "string", "dimension"),
        _tableau_column("segment", "string", "dimension"),
        _tableau_column("category", "string", "dimension"),
        _tableau_column("channel", "string", "dimension"),
        _tableau_column("sku", "string", "dimension"),
        _tableau_column("notes", "string", "dimension"),
        _tableau_column("status", "string", "dimension"),
        _tableau_column("order_date", "date", "dimension"),
    ]
    for formula in scenario.formulas:
        columns.append(
            "      "
            f'<column name="[{_attr(formula.caption)}]" caption="{_attr(formula.caption)}" '
            f'datatype="{_attr(formula.datatype)}" role="{_attr(formula.role)}">'
            f'<calculation class="tableau" formula="{_attr(formula.formula)}" />'
            "</column>"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<workbook version="2024.1">',
                "  <datasources>",
                f'    <datasource name="{scenario.scenario_id.lower()}" caption="{_attr(scenario.name)}">',
                '      <connection class="textscan" />',
                *columns,
                "    </datasource>",
                "  </datasources>",
                "  <worksheets>",
                f'    <worksheet name="{_attr(scenario.name)}" />',
                "  </worksheets>",
                "</workbook>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_alteryx_scenario(scenario: AlteryxScenario, path: Path) -> None:
    nodes = [_alteryx_node(index, tool) for index, tool in enumerate(scenario.tools, start=1)]
    connections = [
        f'    <Connection><Origin ToolID="{index}" Connection="Output" /><Destination ToolID="{index + 1}" Connection="Input" /></Connection>'
        for index in range(1, len(scenario.tools))
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="utf-8"?>',
                '<AlteryxDocument yxmdVer="2024.1">',
                "  <Nodes>",
                *nodes,
                "  </Nodes>",
                "  <Connections>",
                *connections,
                "  </Connections>",
                "</AlteryxDocument>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _tableau_column(name: str, datatype: str, role: str) -> str:
    return f'      <column name="[{name}]" caption="{name}" datatype="{datatype}" role="{role}" />'


def _alteryx_node(tool_id: int, tool: dict) -> str:
    tool_type = tool["type"]
    return "\n".join(
        [
            f'    <Node ToolID="{tool_id}">',
            f'      <GuiSettings Tool="AlteryxBasePluginsGui.{_attr(tool_type)}.{_attr(tool_type)}" />',
            "      <Properties>",
            f'        <Annotation><Name>{_attr(tool.get("name", tool_type))}</Name></Annotation>',
            *_alteryx_properties(tool),
            "      </Properties>",
            "    </Node>",
        ]
    )


def _alteryx_properties(tool: dict) -> list[str]:
    tool_type = tool["type"]
    if tool_type == "Filter":
        return [f"        <Expression>{_attr(tool['expression'])}</Expression>"]
    if tool_type in {"Formula", "MultiRowFormula"}:
        formulas = [
            f'          <FormulaField field="{_attr(field)}" expression="{_attr(expression)}" />'
            for field, expression in tool.get("formulas", [])
        ]
        return ["        <FormulaFields>", *formulas, "        </FormulaFields>"]
    if tool_type == "Summarize":
        fields = [f'          <SummarizeField field="{_attr(field)}" action="GroupBy" />' for field in tool.get("group_by", [])]
        fields.extend(
            f'          <SummarizeField field="{_attr(field)}" action="{_attr(action)}" rename="{_attr(rename)}" />'
            for field, action, rename in tool.get("aggregations", [])
        )
        return ["        <SummarizeFields>", *fields, "        </SummarizeFields>"]
    if tool_type == "Sort":
        fields = [f'          <Field field="{_attr(field)}" order="{_attr(order)}" />' for field, order in tool.get("sort", [])]
        return ["        <SortInfo>", *fields, "        </SortInfo>"]
    if tool_type == "Select":
        fields = [f'          <SelectField field="{_attr(field)}" selected="True" />' for field in tool.get("fields", [])]
        return ["        <SelectFields>", *fields, "        </SelectFields>"]
    if tool_type == "Join":
        return [
            f'        <LeftField field="{_attr(tool.get("left_key", "join_key"))}" />',
            f'        <RightField field="{_attr(tool.get("right_key", "join_key"))}" />',
            f'        <JoinType>{_attr(tool.get("join_type", "LeftOuter"))}</JoinType>',
        ]
    if tool_type == "Unique":
        fields = [f'        <UniqueField field="{_attr(field)}" />' for field in tool.get("fields", [])]
        return fields
    if tool_type == "Sample":
        return [f'        <Sample count="{_attr(tool.get("count", "100"))}" />']
    if tool_type == "RecordID":
        return [f'        <RecordID field="{_attr(tool.get("field", "row_id"))}" start="{_attr(tool.get("start", "1"))}" />']
    if tool_type == "TextToColumns":
        columns = [f'          <Column name="{_attr(column)}" />' for column in tool.get("columns", [])]
        return [
            f'        <Split field="{_attr(tool.get("field", "combined_value"))}" delimiter="{_attr(tool.get("delimiter", "|"))}" />',
            "        <Columns>",
            *columns,
            "        </Columns>",
        ]
    if tool_type == "Transpose":
        return [f'        <KeyField field="{_attr(field)}" />' for field in tool.get("key_fields", [])]
    if tool_type == "CrossTab":
        return [
            f'        <CrossTab group="{_attr(tool.get("group", "region"))}" header="{_attr(tool.get("header", "category"))}" value="{_attr(tool.get("value", "sales_amount"))}" />'
        ]
    if tool_type == "DataCleansing":
        return [f'        <CleanseField field="{_attr(field)}" />' for field in tool.get("fields", [])]
    if tool_type == "Regex":
        return [
            f'        <Regex field="{_attr(tool.get("field", "description"))}" output="{_attr(tool.get("output", "regex_result"))}" pattern="{_attr(tool.get("pattern", "(.*)"))}" />'
        ]
    if tool_type == "DateTime":
        return [
            f'        <DateTime field="{_attr(tool.get("field", "order_date"))}" output="{_attr(tool.get("output", ""))}" />'
        ]
    return []


def _attr(value: object) -> str:
    return html.escape(str(value), quote=True)

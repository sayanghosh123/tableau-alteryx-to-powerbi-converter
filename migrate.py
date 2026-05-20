#!/usr/bin/env python3
"""
Tableau and Alteryx to Power BI migration accelerator.

The tool parses Tableau workbook XML (.twb) and Alteryx workflow XML (.yxmd),
builds an inventory, translates common patterns into draft Power BI artifacts,
and writes a review report. Outputs are migration scaffolds intended for expert
review, not one-click production deployments.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_FACT_TABLE = "Sales"
DEFAULT_DATE_TABLE = "Date"


LLM_PROVIDERS = {
    "none": {
        "description": "Offline rule-based translation",
        "default_model": None,
        "api_key_env": None,
        "client_type": None,
        "base_url": None,
    },
    "azure": {
        "description": "Azure OpenAI (--llm-endpoint plus AZURE_OPENAI_KEY)",
        "default_model": "gpt-4o",
        "api_key_env": "AZURE_OPENAI_KEY",
        "client_type": "azure",
        "base_url": None,
    },
    "openai": {
        "description": "OpenAI API (OPENAI_API_KEY)",
        "default_model": "gpt-4o",
        "api_key_env": "OPENAI_API_KEY",
        "client_type": "openai",
        "base_url": "https://api.openai.com/v1",
    },
    "github": {
        "description": "GitHub Models (GITHUB_TOKEN)",
        "default_model": "gpt-4o",
        "api_key_env": "GITHUB_TOKEN",
        "client_type": "openai",
        "base_url": "https://models.inference.ai.azure.com",
    },
    "custom": {
        "description": "Any OpenAI-compatible endpoint (--llm-endpoint plus OPENAI_API_KEY)",
        "default_model": "gpt-4o",
        "api_key_env": "OPENAI_API_KEY",
        "client_type": "openai",
        "base_url": None,
    },
}


@dataclass
class TableauField:
    name: str
    caption: str
    formula: str
    field_type: str
    datatype: str
    role: str


@dataclass
class TableauDatasource:
    name: str
    caption: str
    connection_type: str
    calculated_fields: list[TableauField]


@dataclass
class AlteryxTool:
    tool_id: str
    tool_type: str
    annotation: str
    expressions: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)


@dataclass
class MigrationResult:
    source_item: str
    source_type: str
    output_type: str
    output_code: str
    confidence: float
    flags: list[str]
    notes: str = ""
    output_name: str = ""


class LLMClient:
    """Small wrapper around OpenAI-compatible chat completion clients."""

    def __init__(
        self,
        provider: str,
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ):
        cfg = LLM_PROVIDERS[provider]
        key_env = cfg["api_key_env"]
        resolved_key = api_key or (os.environ.get(key_env) if key_env else None)
        if not resolved_key:
            raise EnvironmentError(
                f"No API key for provider '{provider}'. Set {key_env} or pass --llm-api-key."
            )

        self.provider = provider
        self.model = model or cfg["default_model"]

        if cfg["client_type"] == "azure":
            if not endpoint:
                raise ValueError("--llm-endpoint is required for provider 'azure'.")
            from openai import AzureOpenAI

            self._client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_key=resolved_key,
                api_version="2024-08-01-preview",
            )
            return

        from openai import OpenAI

        self._client = OpenAI(
            base_url=endpoint or cfg["base_url"],
            api_key=resolved_key,
        )

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "LLMClient | None":
        if args.llm_provider == "none":
            return None
        try:
            return cls(
                provider=args.llm_provider,
                endpoint=args.llm_endpoint,
                model=args.llm_model,
                api_key=args.llm_api_key,
            )
        except (EnvironmentError, ValueError) as exc:
            print(f"LLM disabled: {exc}", file=sys.stderr)
            return None

    def complete(self, system: str, user: str, max_tokens: int = 1200) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()


class DiscoveryAgent:
    """Reads source XML files and returns a neutral migration inventory."""

    def discover_tableau(self, path: Path) -> list[TableauDatasource]:
        root = _parse_xml(path)
        datasources: list[TableauDatasource] = []

        for ds in _iter_tag(root, "datasource"):
            name = ds.get("name", "")
            caption = ds.get("caption", "") or name
            if not name or name == "Parameters" or caption == "Parameters":
                continue

            conn = _find_first(ds, "connection")
            connection_type = conn.get("class", "unknown") if conn is not None else "unknown"
            calc_fields = []

            for col in _iter_tag(ds, "column"):
                calc = _find_first(col, "calculation")
                if calc is None:
                    continue
                formula = (calc.get("formula") or "").strip()
                if not formula:
                    continue

                raw_name = col.get("name", "")
                raw_caption = col.get("caption", "") or raw_name
                field = TableauField(
                    name=_clean_tableau_name(raw_name),
                    caption=_clean_tableau_name(raw_caption),
                    formula=formula,
                    field_type=_classify_tableau_field(formula),
                    datatype=col.get("datatype", "real"),
                    role=col.get("role", "measure"),
                )
                calc_fields.append(field)

            datasources.append(
                TableauDatasource(
                    name=name,
                    caption=caption,
                    connection_type=connection_type,
                    calculated_fields=calc_fields,
                )
            )

        return datasources

    def discover_alteryx(self, path: Path) -> list[AlteryxTool]:
        root = _parse_xml(path)
        tools: list[AlteryxTool] = []

        for node in _iter_tag(root, "Node"):
            tool_id = node.get("ToolID", "?")
            gui = _find_first(node, "GuiSettings")
            props = _find_first(node, "Properties")
            if gui is None:
                continue

            annotation = _annotation(node) or f"Tool {tool_id}"
            tool_type = _classify_alteryx_tool(gui.get("Tool", ""))
            expressions = _extract_alteryx_expressions(tool_type, props)
            config = _extract_alteryx_config(tool_type, props)

            tools.append(
                AlteryxTool(
                    tool_id=tool_id,
                    tool_type=tool_type,
                    annotation=annotation,
                    expressions=expressions,
                    config=config,
                )
            )

        tools.sort(key=lambda t: _natural_key(t.tool_id))
        return tools


class AnalyzerAgent:
    """Computes relative complexity and review effort."""

    FIELD_WEIGHTS = {
        "lod_fixed": 3.5,
        "lod_include": 3.0,
        "lod_exclude": 3.0,
        "table_calc": 2.5,
        "basic": 1.0,
    }

    TOOL_WEIGHTS = {
        "Input": 0.5,
        "Output": 0.5,
        "Filter": 1.0,
        "Formula": 1.0,
        "Join": 2.0,
        "MultiRowFormula": 3.5,
        "Select": 0.5,
        "Sort": 0.5,
        "Summarize": 1.5,
        "Union": 2.0,
        "Unknown": 4.0,
    }

    def analyze(
        self, datasources: list[TableauDatasource], tools: list[AlteryxTool]
    ) -> dict:
        fields = [field for ds in datasources for field in ds.calculated_fields]
        field_effort = sum(self.FIELD_WEIGHTS.get(f.field_type, 1.0) for f in fields)
        tool_effort = sum(self.TOOL_WEIGHTS.get(t.tool_type, 1.0) for t in tools)
        manual_hours = round((field_effort + tool_effort) * 4.0, 1)
        accelerator_hours = round((field_effort + tool_effort) * 1.5, 1)
        saving_pct = round((1 - accelerator_hours / manual_hours) * 100) if manual_hours else 0

        return {
            "tableau_datasources": len(datasources),
            "tableau_fields": len(fields),
            "tableau_lod": sum(1 for f in fields if f.field_type.startswith("lod")),
            "tableau_table_calcs": sum(1 for f in fields if f.field_type == "table_calc"),
            "alteryx_tools": len(tools),
            "field_complexity_units": round(field_effort, 1),
            "workflow_complexity_units": round(tool_effort, 1),
            "manual_hours": manual_hours,
            "accelerator_hours": accelerator_hours,
            "saving_pct": saving_pct,
        }


class TranslatorAgent:
    """Converts known patterns to DAX/TMDL and Power Query M scaffolds."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        fact_table: str = DEFAULT_FACT_TABLE,
        date_table: str = DEFAULT_DATE_TABLE,
    ):
        self.llm = llm_client
        self.fact_table = fact_table
        self.date_table = date_table

    def translate_tableau(
        self, datasources: list[TableauDatasource], output_dir: Path
    ) -> list[MigrationResult]:
        results: list[MigrationResult] = []
        for datasource in datasources:
            for field in datasource.calculated_fields:
                result = self._translate_tableau_field(field)
                if self.llm and result.confidence < 80:
                    result = self._llm_upgrade_dax(field, result)
                results.append(result)

        definition_dir = output_dir / "power_bi" / "definition"
        tables_dir = definition_dir / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        _write_model_tmdl(definition_dir / "model.tmdl")
        _write_fact_table_tmdl(
            tables_dir / f"{self.fact_table}.tmdl",
            datasources,
            [r for r in results if r.output_type == "dax_calc_column"],
            self.fact_table,
        )
        _write_measures_tmdl(
            tables_dir / "_Measures.tmdl",
            [r for r in results if r.output_type == "dax_measure"],
        )
        return results

    def translate_alteryx(
        self, tools: list[AlteryxTool], output_dir: Path, workflow_stem: str
    ) -> list[MigrationResult]:
        results: list[MigrationResult] = []
        previous_step = ""
        input_count = 0

        for tool in tools:
            result = self._translate_alteryx_tool(tool, previous_step)
            if self.llm and result.confidence < 80 and tool.tool_type not in {"Input", "Output"}:
                result = self._llm_upgrade_m(tool, result, previous_step)

            if tool.tool_type == "Input":
                input_count += 1
                if input_count > 1:
                    result.flags.append("Multiple inputs require relationship and join review")
            results.append(result)
            previous_step = result.output_name or previous_step

        dataflow_dir = output_dir / "dataflows"
        dataflow_dir.mkdir(parents=True, exist_ok=True)
        _write_power_query(dataflow_dir / f"{workflow_stem}.pq", results, workflow_stem)
        return results

    def _translate_tableau_field(self, field: TableauField) -> MigrationResult:
        name = _safe_label(field.caption or field.name)
        formula = field.formula.strip()
        output_type = "dax_measure" if field.role == "measure" else "dax_calc_column"
        flags: list[str] = []

        if field.field_type == "lod_fixed":
            expression, confidence = _translate_lod_fixed(formula, self.fact_table)
            if confidence < 85:
                flags.append("Review filter context against the Tableau view grain")
            return MigrationResult(
                source_item=name,
                source_type=field.field_type,
                output_type=output_type,
                output_code=expression,
                confidence=confidence,
                flags=flags,
                notes="FIXED LOD converted to CALCULATE plus ALLEXCEPT",
            )

        if field.field_type in {"lod_include", "lod_exclude"}:
            expression, confidence = _translate_include_exclude_lod(
                formula, self.fact_table, field.field_type
            )
            return MigrationResult(
                source_item=name,
                source_type=field.field_type,
                output_type=output_type,
                output_code=expression,
                confidence=confidence,
                flags=["Review dimensional grain before production use"],
                notes="INCLUDE/EXCLUDE LOD converted to review-ready DAX scaffold",
            )

        if field.field_type == "table_calc":
            expression, confidence = _translate_table_calc(
                formula, self.fact_table, self.date_table
            )
            return MigrationResult(
                source_item=name,
                source_type=field.field_type,
                output_type=output_type,
                output_code=expression,
                confidence=confidence,
                flags=["Verify window context against the original worksheet"],
                notes="Table calculation converted to DAX time/window pattern",
            )

        expression, confidence = _translate_basic_tableau_formula(formula, self.fact_table)
        return MigrationResult(
            source_item=name,
            source_type=field.field_type,
            output_type=output_type,
            output_code=expression,
            confidence=confidence,
            flags=[] if confidence >= 80 else ["Review translated expression"],
        )

    def _translate_alteryx_tool(self, tool: AlteryxTool, previous_step: str) -> MigrationResult:
        step_name = f"Step_{_safe_identifier(tool.tool_id)}"
        previous = previous_step or step_name
        flags: list[str] = []
        confidence = 85.0

        if tool.tool_type == "Input":
            raw_name = f"Raw_{_safe_identifier(tool.tool_id)}"
            code = (
                f'{raw_name} = Csv.Document(File.Contents(SourcePath), '
                '[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
                f"{step_name} = Table.PromoteHeaders({raw_name}, [PromoteAllScalars=true])"
            )
            return MigrationResult(
                tool.annotation,
                "Input",
                "m_step",
                code,
                90.0,
                ["Replace SourcePath with a Fabric Lakehouse, OneLake, or file source"],
                output_name=step_name,
            )

        if tool.tool_type == "Filter":
            expr = tool.expressions[0] if tool.expressions else "true"
            m_expr = _alteryx_expr_to_m(expr)
            code = f"{step_name} = Table.SelectRows({previous}, each {m_expr})"
            return MigrationResult(tool.annotation, "Filter", "m_step", code, 88.0, [], output_name=step_name)

        if tool.tool_type == "Formula":
            if not tool.expressions:
                flags.append("Formula tool had no expressions")
                return MigrationResult(
                    tool.annotation,
                    "Formula",
                    "m_step",
                    f"{step_name} = {previous}",
                    65.0,
                    flags,
                    output_name=step_name,
                )

            transforms = []
            for expression in tool.expressions:
                col_name, col_expr = _split_assignment(expression)
                transforms.append(
                    f'(t as table) => Table.AddColumn(t, "{_escape_m_text(col_name)}", '
                    f"each {_alteryx_expr_to_m(col_expr)}, type any)"
                )
            code = (
                f"{step_name} = List.Accumulate(\n"
                f"        {{\n            {',\n            '.join(transforms)}\n"
                f"        }},\n"
                f"        {previous},\n"
                f"        (state as table, transform as function) => transform(state)\n"
                f"    )"
            )
            return MigrationResult(tool.annotation, "Formula", "m_step", code, 86.0, [], output_name=step_name)

        if tool.tool_type == "MultiRowFormula":
            indexed = f"Indexed_{_safe_identifier(tool.tool_id)}"
            output_field = _multirow_output_field(tool)
            value_field = _first_field_reference(" ".join(tool.expressions)) or "sales_amount"
            code = (
                f'{indexed} = Table.AddIndexColumn({previous}, "_RowNumber", 0, 1, Int64.Type),\n'
                f'{step_name} = Table.AddColumn({indexed}, "{_escape_m_text(output_field)}", '
                f'each List.Sum(List.FirstN({indexed}[{_m_identifier(value_field)}], [#"_RowNumber"] + 1)), type number)'
            )
            return MigrationResult(
                tool.annotation,
                "MultiRowFormula",
                "m_step",
                code,
                72.0,
                ["Review partitioning and ordering for multi-row logic"],
                output_name=step_name,
            )

        if tool.tool_type == "Summarize":
            group_fields = tool.config.get("group_by") or ["region"]
            aggregations = tool.config.get("aggregations") or [
                {"field": "sales_amount", "action": "Sum", "name": "total_sales"}
            ]
            group_text = ", ".join(f'"{_escape_m_text(f)}"' for f in group_fields)
            agg_text = ",\n            ".join(_summarize_aggregation_to_m(a) for a in aggregations)
            code = f"{step_name} = Table.Group({previous}, {{{group_text}}}, {{\n            {agg_text}\n        }})"
            return MigrationResult(tool.annotation, "Summarize", "m_step", code, 90.0, [], output_name=step_name)

        if tool.tool_type == "Sort":
            sort_fields = tool.config.get("sort_fields") or [{"field": "order_date", "order": "Ascending"}]
            sort_text = ", ".join(
                f'{{"{_escape_m_text(item["field"])}", {_m_sort_order(item.get("order", "Ascending"))}}}'
                for item in sort_fields
            )
            code = f"{step_name} = Table.Sort({previous}, {{{sort_text}}})"
            return MigrationResult(tool.annotation, "Sort", "m_step", code, 96.0, [], output_name=step_name)

        if tool.tool_type == "Select":
            fields = tool.config.get("select_fields") or []
            if fields:
                field_text = ", ".join(f'"{_escape_m_text(f)}"' for f in fields)
                code = f"{step_name} = Table.SelectColumns({previous}, {{{field_text}}}, MissingField.Ignore)"
            else:
                code = f"{step_name} = {previous}"
                flags.append("No selected fields found")
            return MigrationResult(tool.annotation, "Select", "m_step", code, 82.0, flags, output_name=step_name)

        if tool.tool_type == "Join":
            left_key = tool.config.get("left_key", "join_key")
            right_key = tool.config.get("right_key", left_key)
            join_kind = _join_kind_to_m(tool.config.get("join_type", "LeftOuter"))
            code = (
                f'{step_name} = Table.NestedJoin({previous}, {{"{_escape_m_text(left_key)}"}}, '
                f'{previous}, {{"{_escape_m_text(right_key)}"}}, "JoinedRows", {join_kind})'
            )
            return MigrationResult(
                tool.annotation,
                "Join",
                "m_step",
                code,
                70.0,
                ["Connect the correct left and right input steps before production use"],
                output_name=step_name,
            )

        if tool.tool_type == "Union":
            code = f"{step_name} = Table.Combine({{{previous}}})"
            return MigrationResult(
                tool.annotation,
                "Union",
                "m_step",
                code,
                70.0,
                ["Add all source tables to the Table.Combine list"],
                output_name=step_name,
            )

        if tool.tool_type == "Output":
            code = f"{step_name} = {previous}"
            return MigrationResult(
                tool.annotation,
                "Output",
                "m_step",
                code,
                80.0,
                ["Bind this final step to the target Fabric destination"],
                output_name=step_name,
            )

        return MigrationResult(
            tool.annotation,
            tool.tool_type,
            "m_step",
            f"{step_name} = {previous}",
            40.0,
            [f"Unsupported tool type: {tool.tool_type}"],
            output_name=step_name,
        )

    def _llm_upgrade_dax(self, field: TableauField, fallback: MigrationResult) -> MigrationResult:
        system = (
            "You are a Power BI DAX expert. Convert Tableau calculated fields to a "
            "single DAX expression body. Return only the expression body, not a measure name."
        )
        user = (
            f"Field: {field.caption or field.name}\n"
            f"Role: {field.role}\n"
            f"Formula:\n{field.formula}\n"
            f"Default fact table: {self.fact_table}"
        )
        try:
            expression = self.llm.complete(system, user)
        except Exception as exc:
            fallback.flags.append(f"LLM upgrade failed: {exc}")
            return fallback
        return MigrationResult(
            fallback.source_item,
            fallback.source_type,
            fallback.output_type,
            expression,
            90.0,
            fallback.flags,
            notes=f"LLM-assisted with {self.llm.provider}/{self.llm.model}",
        )

    def _llm_upgrade_m(
        self, tool: AlteryxTool, fallback: MigrationResult, previous_step: str
    ) -> MigrationResult:
        system = (
            "You are a Power Query M expert. Convert this Alteryx tool to valid "
            "Power Query M let-step assignments. Return only assignments."
        )
        user = (
            f"Tool type: {tool.tool_type}\n"
            f"Annotation: {tool.annotation}\n"
            f"Previous step: {previous_step}\n"
            f"Expressions: {tool.expressions}\n"
            f"Config: {tool.config}"
        )
        try:
            code = self.llm.complete(system, user)
        except Exception as exc:
            fallback.flags.append(f"LLM upgrade failed: {exc}")
            return fallback
        return MigrationResult(
            fallback.source_item,
            fallback.source_type,
            fallback.output_type,
            code,
            88.0,
            fallback.flags,
            notes=f"LLM-assisted with {self.llm.provider}/{self.llm.model}",
            output_name=fallback.output_name,
        )


class ValidatorAgent:
    """Performs lightweight structural checks on generated code."""

    def validate(
        self, tableau_results: list[MigrationResult], alteryx_results: list[MigrationResult]
    ) -> dict:
        dax_pass = dax_warn = dax_fail = 0
        m_pass = m_warn = m_fail = 0

        for result in tableau_results:
            issues = _check_dax(result.output_code)
            if not issues:
                dax_pass += 1
            elif result.confidence >= 70:
                dax_warn += 1
                result.flags.extend(issues)
            else:
                dax_fail += 1
                result.flags.extend(issues)

        for result in alteryx_results:
            issues = _check_m(result.output_code)
            if not issues:
                m_pass += 1
            elif result.confidence >= 70:
                m_warn += 1
                result.flags.extend(issues)
            else:
                m_fail += 1
                result.flags.extend(issues)

        all_results = tableau_results + alteryx_results
        avg_confidence = round(
            sum(r.confidence for r in all_results) / len(all_results), 1
        ) if all_results else 0.0

        return {
            "dax_pass": dax_pass,
            "dax_warn": dax_warn,
            "dax_fail": dax_fail,
            "m_pass": m_pass,
            "m_warn": m_warn,
            "m_fail": m_fail,
            "avg_confidence": avg_confidence,
            "auto_migrate": sum(1 for r in all_results if r.confidence >= 80),
            "needs_review": sum(1 for r in all_results if 60 <= r.confidence < 80),
            "needs_manual": sum(1 for r in all_results if r.confidence < 60),
            "total": len(all_results),
        }


class ReporterAgent:
    """Writes a neutral HTML report for the migration review."""

    def report(
        self,
        report_dir: Path,
        analysis: dict,
        validation: dict,
        tableau_results: list[MigrationResult],
        alteryx_results: list[MigrationResult],
    ) -> Path:
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "migration_report.html"
        report_path.write_text(
            _build_html_report(analysis, validation, tableau_results, alteryx_results),
            encoding="utf-8",
        )
        return report_path


def _parse_xml(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise SystemExit(f"Invalid XML in {path}: {exc}") from exc
    except OSError as exc:
        raise SystemExit(f"Cannot read {path}: {exc}") from exc


def _tag_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _iter_tag(element: ET.Element, tag: str) -> Iterable[ET.Element]:
    for child in element.iter():
        if _tag_name(child) == tag:
            yield child


def _children_tag(element: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in list(element) if _tag_name(child) == tag]


def _find_first(element: ET.Element | None, tag: str) -> ET.Element | None:
    if element is None:
        return None
    return next(_iter_tag(element, tag), None)


def _annotation(node: ET.Element) -> str:
    for name_tag in _iter_tag(node, "Name"):
        text = (name_tag.text or "").strip()
        if text:
            return text
    return ""


def _extract_alteryx_expressions(tool_type: str, props: ET.Element | None) -> list[str]:
    if props is None:
        return []
    expressions: list[str] = []

    if tool_type in {"Formula", "MultiRowFormula"}:
        for formula_field in _iter_tag(props, "FormulaField"):
            field_name = formula_field.get("field") or formula_field.get("name") or "calculated_field"
            expression = formula_field.get("expression") or (formula_field.text or "")
            if expression.strip():
                expressions.append(f"{field_name.strip()} = {expression.strip()}")

    if tool_type == "Filter":
        expression = _find_first(props, "Expression")
        if expression is not None and expression.text:
            expressions.append(expression.text.strip())

    return expressions


def _extract_alteryx_config(tool_type: str, props: ET.Element | None) -> dict:
    if props is None:
        return {}

    if tool_type == "Summarize":
        group_by = []
        aggregations = []
        for field in _iter_tag(props, "SummarizeField"):
            action = field.get("action", "")
            source_field = field.get("field", "")
            rename = field.get("rename") or field.get("name") or _default_aggregation_name(action, source_field)
            if action.lower() == "groupby":
                group_by.append(source_field)
            elif source_field:
                aggregations.append({"field": source_field, "action": action, "name": rename})
        return {"group_by": group_by, "aggregations": aggregations}

    if tool_type == "Sort":
        fields = []
        for field in _iter_tag(props, "Field"):
            field_name = field.get("field") or field.get("name")
            if field_name:
                fields.append({"field": field_name, "order": field.get("order", "Ascending")})
        return {"sort_fields": fields}

    if tool_type == "Select":
        fields = []
        for field in _iter_tag(props, "SelectField"):
            field_name = field.get("field") or field.get("name")
            selected = field.get("selected", "True").lower() != "false"
            if field_name and selected:
                fields.append(field_name)
        return {"select_fields": fields}

    if tool_type == "Join":
        left = _find_first(props, "LeftField")
        right = _find_first(props, "RightField")
        return {
            "left_key": left.get("field") if left is not None else "join_key",
            "right_key": right.get("field") if right is not None else "join_key",
            "join_type": (_find_first(props, "JoinType").text or "LeftOuter")
            if _find_first(props, "JoinType") is not None
            else "LeftOuter",
        }

    return {}


def _classify_tableau_field(formula: str) -> str:
    text = formula.upper()
    if "{" in formula:
        if "FIXED" in text:
            return "lod_fixed"
        if "INCLUDE" in text:
            return "lod_include"
        if "EXCLUDE" in text:
            return "lod_exclude"
    if any(keyword in text for keyword in ("RUNNING_SUM", "WINDOW_SUM", "LOOKUP", "TOTAL(")):
        return "table_calc"
    return "basic"


def _classify_alteryx_tool(tool_attr: str) -> str:
    mapping = {
        "DbFileInput": "Input",
        "Input": "Input",
        "DbFileOutput": "Output",
        "Output": "Output",
        "MultiRowFormula": "MultiRowFormula",
        "AlteryxFormula": "Formula",
        "Formula": "Formula",
        "AlteryxFilter": "Filter",
        "Filter": "Filter",
        "AlteryxJoin": "Join",
        "Join": "Join",
        "AlteryxSummarize": "Summarize",
        "Summarize": "Summarize",
        "AlteryxSort": "Sort",
        "Sort": "Sort",
        "AlteryxUnion": "Union",
        "Union": "Union",
        "AlteryxSelect": "Select",
        "Select": "Select",
    }
    for needle, tool_type in mapping.items():
        if needle in tool_attr:
            return tool_type
    return "Unknown"


def _translate_lod_fixed(formula: str, table: str) -> tuple[str, float]:
    match = re.match(r"\{\s*FIXED\s+(.*?)\s*:\s*(.*?)\s*\}", formula, re.IGNORECASE | re.DOTALL)
    if not match:
        return _tableau_agg_to_dax(formula, table), 55.0

    dimensions = [
        _clean_tableau_name(part)
        for part in re.findall(r"\[([^\]]+)\]", match.group(1))
    ]
    expression = _tableau_agg_to_dax(match.group(2), table)
    if not dimensions:
        return f"CALCULATE({expression}, ALL('{table}'))", 78.0

    dimension_text = ", ".join(_dax_column(table, dimension) for dimension in dimensions)
    return f"CALCULATE({expression}, ALLEXCEPT('{table}', {dimension_text}))", 85.0


def _translate_include_exclude_lod(formula: str, table: str, field_type: str) -> tuple[str, float]:
    match = re.match(
        r"\{\s*(INCLUDE|EXCLUDE)\s+(.*?)\s*:\s*(.*?)\s*\}",
        formula,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return _tableau_agg_to_dax(formula, table), 55.0
    dimensions = [_clean_tableau_name(part) for part in re.findall(r"\[([^\]]+)\]", match.group(2))]
    expression = _tableau_agg_to_dax(match.group(3), table)
    if field_type == "lod_include":
        filters = ", ".join(f"VALUES({_dax_column(table, dimension)})" for dimension in dimensions)
    else:
        filters = ", ".join(f"REMOVEFILTERS({_dax_column(table, dimension)})" for dimension in dimensions)
    return f"CALCULATE({expression}, {filters})" if filters else expression, 68.0


def _translate_table_calc(formula: str, table: str, date_table: str) -> tuple[str, float]:
    text = formula.upper()
    if "RUNNING_SUM" in text:
        inner = _first_function_argument(formula, "RUNNING_SUM") or "SUM([sales_amount])"
        expression = _tableau_agg_to_dax(inner, table)
        return (
            "CALCULATE("
            f"{expression}, "
            f"FILTER(ALLSELECTED('{date_table}'[Date]), '{date_table}'[Date] <= MAX('{date_table}'[Date]))"
            ")",
            82.0,
        )

    if "LOOKUP" in text:
        args = _split_args(_first_function_argument(formula, "LOOKUP") or "")
        expression = _tableau_agg_to_dax(args[0], table) if args else f"SUM({_dax_column(table, 'sales_amount')})"
        offset = args[1].strip() if len(args) > 1 else "-1"
        return (
            f"CALCULATE({expression}, DATEADD('{date_table}'[Date], {offset}, MONTH))",
            78.0,
        )

    if "TOTAL(" in text:
        if "/" in formula:
            numerator_raw, denominator_raw = formula.split("/", 1)
            numerator = _tableau_agg_to_dax(numerator_raw.strip(), table)
            inner = _first_function_argument(denominator_raw, "TOTAL") or denominator_raw
            denominator = _tableau_agg_to_dax(inner, table)
            return f"DIVIDE({numerator}, CALCULATE({denominator}, ALL('{table}')))", 86.0
        inner = _first_function_argument(formula, "TOTAL") or "SUM([sales_amount])"
        expression = _tableau_agg_to_dax(inner, table)
        return f"CALCULATE({expression}, ALL('{table}'))", 86.0

    return _tableau_agg_to_dax(formula, table), 55.0


def _translate_basic_tableau_formula(formula: str, table: str) -> tuple[str, float]:
    stripped = formula.strip()
    if re.match(r"^IF\b", stripped, re.IGNORECASE):
        return _translate_tableau_if(stripped, table), 82.0
    if re.match(r"^CASE\b", stripped, re.IGNORECASE):
        return _translate_tableau_case(stripped, table), 76.0
    return _convert_tableau_expr(stripped, table), 90.0


def _translate_tableau_if(formula: str, table: str) -> str:
    body = re.sub(r"^IF\s+", "", formula.strip(), flags=re.IGNORECASE)
    body = re.sub(r"\s+END(IF)?\s*$", "", body, flags=re.IGNORECASE)
    else_part = "BLANK()"
    else_match = re.search(r"\bELSE\b(?!IF)(.*)$", body, re.IGNORECASE | re.DOTALL)
    if else_match:
        else_part = _convert_tableau_scalar(else_match.group(1).strip(), table)
        body = body[: else_match.start()].strip()

    clauses = re.split(r"\bELSEIF\b", body, flags=re.IGNORECASE)
    expression = else_part
    for clause in reversed(clauses):
        match = re.match(r"\s*(.*?)\s+THEN\s+(.*?)\s*$", clause, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        condition = _convert_tableau_expr(match.group(1), table)
        value = _convert_tableau_scalar(match.group(2), table)
        expression = f"IF({condition}, {value}, {expression})"
    return expression


def _translate_tableau_case(formula: str, table: str) -> str:
    whens = re.findall(
        r"WHEN\s+(.*?)\s+THEN\s+(.*?)(?=\s+WHEN|\s+ELSE|\s+END)",
        formula,
        re.IGNORECASE | re.DOTALL,
    )
    else_match = re.search(r"\bELSE\b(.*?)\bEND\b", formula, re.IGNORECASE | re.DOTALL)
    parts = ["SWITCH(TRUE()"]
    for condition, value in whens:
        parts.append(f", {_convert_tableau_expr(condition, table)}, {_convert_tableau_scalar(value, table)}")
    if else_match:
        parts.append(f", {_convert_tableau_scalar(else_match.group(1), table)}")
    parts.append(")")
    return "".join(parts)


def _convert_tableau_scalar(value: str, table: str) -> str:
    stripped = value.strip()
    if re.match(r"^-?\d+(\.\d+)?$", stripped):
        return stripped
    if (stripped.startswith("'") and stripped.endswith("'")) or (
        stripped.startswith('"') and stripped.endswith('"')
    ):
        return f'"{stripped[1:-1]}"'
    if stripped.upper() == "NULL":
        return "BLANK()"
    return _convert_tableau_expr(stripped, table)


def _convert_tableau_expr(expression: str, table: str) -> str:
    converted = _normalize_tableau_strings(expression)
    converted = _tableau_agg_to_dax(converted, table)
    converted = re.sub(
        r"DATEDIFF\(\s*'day'\s*,\s*(.*?)\s*,\s*TODAY\(\)\s*\)",
        r"DATEDIFF(\1, TODAY(), DAY)",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(
        r"DATEDIFF\(\s*'month'\s*,\s*(.*?)\s*,\s*TODAY\(\)\s*\)",
        r"DATEDIFF(\1, TODAY(), MONTH)",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(
        r"DATEDIFF\(\s*'year'\s*,\s*(.*?)\s*,\s*TODAY\(\)\s*\)",
        r"DATEDIFF(\1, TODAY(), YEAR)",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(r"\bAND\b", "&&", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bOR\b", "||", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bZN\(", "COALESCE(", converted, flags=re.IGNORECASE)
    converted = _replace_remaining_tableau_fields(converted, table)
    return converted


def _tableau_agg_to_dax(formula: str, table: str) -> str:
    converted = formula
    replacements = {
        "COUNTD": "DISTINCTCOUNT",
        "COUNT": "COUNT",
        "SUM": "SUM",
        "AVG": "AVERAGE",
        "AVERAGE": "AVERAGE",
        "MIN": "MIN",
        "MAX": "MAX",
    }
    for tableau_function, dax_function in replacements.items():
        converted = re.sub(
            rf"\b{tableau_function}\s*\(\s*\[([^\]]+)\]\s*\)",
            lambda match: f"{dax_function}({_dax_column(table, match.group(1))})",
            converted,
            flags=re.IGNORECASE,
        )
    return converted


def _replace_remaining_tableau_fields(expression: str, table: str) -> str:
    return re.sub(r"(?<!')\[([^\]]+)\]", lambda match: _dax_column(table, match.group(1)), expression)


def _normalize_tableau_strings(expression: str) -> str:
    return re.sub(r"'([^']*)'", lambda match: f'"{match.group(1)}"', expression)


def _dax_column(table: str, column: str) -> str:
    return f"'{table}'[{_clean_tableau_name(column)}]"


def _alteryx_expr_to_m(expression: str) -> str:
    converted = expression.strip()
    converted = _replace_iif(converted)
    converted = re.sub(
        r"!\s*IsNull\(\s*\[([^\]]+)\]\s*\)",
        lambda m: f"{_m_field(m.group(1))} <> null",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(
        r"!\s*IsEmpty\(\s*\[([^\]]+)\]\s*\)",
        lambda m: f"not ({_m_field(m.group(1))} = null or Text.Length(Text.From({_m_field(m.group(1))})) = 0)",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(
        r"IsNull\(\s*\[([^\]]+)\]\s*\)",
        lambda m: f"{_m_field(m.group(1))} = null",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(
        r"IsEmpty\(\s*\[([^\]]+)\]\s*\)",
        lambda m: f"({_m_field(m.group(1))} = null or Text.Length(Text.From({_m_field(m.group(1))})) = 0)",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(r"\bAND\b", "and", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bOR\b", "or", converted, flags=re.IGNORECASE)
    converted = converted.replace("!=", "<>")
    converted = re.sub(r"(?<![<>=])!(?!=)", "not ", converted)
    converted = re.sub(r"\bDateTimeToday\(\)", "Date.From(DateTime.LocalNow())", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bUppercase\(", "Text.Upper(", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bLowercase\(", "Text.Lower(", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bTrim\(", "Text.Trim(", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bToString\(", "Text.From(", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\bToNumber\(", "Number.From(", converted, flags=re.IGNORECASE)
    converted = re.sub(r"\[([^\]]+)\]", lambda m: _m_field(m.group(1)), converted)
    return converted


def _replace_iif(expression: str) -> str:
    result = expression
    while True:
        match = re.search(r"\bIIF\(", result, re.IGNORECASE)
        if not match:
            return result
        start = match.end()
        end = _find_matching_paren(result, start - 1)
        if end == -1:
            return result
        args = _split_args(result[start:end])
        if len(args) != 3:
            return result
        replacement = f"if {_alteryx_expr_to_m(args[0])} then {_alteryx_expr_to_m(args[1])} else {_alteryx_expr_to_m(args[2])}"
        result = result[: match.start()] + replacement + result[end + 1 :]


def _find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    in_quote = False
    quote_char = ""
    for index in range(open_index, len(text)):
        char = text[index]
        if char in {'"', "'"}:
            if in_quote and char == quote_char:
                in_quote = False
            elif not in_quote:
                in_quote = True
                quote_char = char
        if in_quote:
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _split_args(text: str) -> list[str]:
    args: list[str] = []
    current: list[str] = []
    depth = 0
    in_quote = False
    quote_char = ""
    for char in text:
        if char in {'"', "'"}:
            if in_quote and char == quote_char:
                in_quote = False
            elif not in_quote:
                in_quote = True
                quote_char = char
        elif not in_quote:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                args.append("".join(current).strip())
                current = []
                continue
        current.append(char)
    if current:
        args.append("".join(current).strip())
    return args


def _first_function_argument(formula: str, function_name: str) -> str | None:
    match = re.search(rf"\b{re.escape(function_name)}\s*\(", formula, re.IGNORECASE)
    if not match:
        return None
    end = _find_matching_paren(formula, match.end() - 1)
    if end == -1:
        return None
    return formula[match.end() : end]


def _split_assignment(expression: str) -> tuple[str, str]:
    if " = " in expression:
        left, right = expression.split(" = ", 1)
        return left.strip(), right.strip()
    return "calculated_field", expression.strip()


def _multirow_output_field(tool: AlteryxTool) -> str:
    if tool.expressions:
        return _split_assignment(tool.expressions[0])[0]
    return "running_total"


def _first_field_reference(expression: str) -> str | None:
    for field_name in re.findall(r"\[([^\]]+)\]", expression):
        lowered = field_name.lower()
        if ":" not in field_name and not lowered.startswith("row"):
            return field_name
    return None


def _summarize_aggregation_to_m(aggregation: dict) -> str:
    action = (aggregation.get("action") or "Sum").lower()
    field = aggregation.get("field", "sales_amount")
    name = aggregation.get("name") or _default_aggregation_name(action, field)
    column = _m_identifier(field)
    if action in {"sum", "total"}:
        return f'{{"{_escape_m_text(name)}", each List.Sum([{column}]), type number}}'
    if action in {"avg", "average", "mean"}:
        return f'{{"{_escape_m_text(name)}", each List.Average([{column}]), type number}}'
    if action == "max":
        return f'{{"{_escape_m_text(name)}", each List.Max([{column}]), type any}}'
    if action == "min":
        return f'{{"{_escape_m_text(name)}", each List.Min([{column}]), type any}}'
    if action in {"count", "countrows"}:
        return f'{{"{_escape_m_text(name)}", each Table.RowCount(_), Int64.Type}}'
    return f'{{"{_escape_m_text(name)}", each List.Sum([{column}]), type number}}'


def _default_aggregation_name(action: str, field: str) -> str:
    base = field or "rows"
    action_text = action.lower() if action else "sum"
    return f"{action_text}_{base}"


def _m_field(name: str) -> str:
    return f"[{_m_identifier(name)}]"


def _m_identifier(name: str) -> str:
    clean = str(name).replace('"', '""')
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", clean):
        return clean
    return f'#"{clean}"'


def _m_sort_order(order: str) -> str:
    return "Order.Descending" if "desc" in order.lower() else "Order.Ascending"


def _join_kind_to_m(join_type: str) -> str:
    normalized = (join_type or "").replace(" ", "").lower()
    mapping = {
        "inner": "JoinKind.Inner",
        "left": "JoinKind.LeftOuter",
        "leftouter": "JoinKind.LeftOuter",
        "right": "JoinKind.RightOuter",
        "rightouter": "JoinKind.RightOuter",
        "fullouter": "JoinKind.FullOuter",
    }
    return mapping.get(normalized, "JoinKind.LeftOuter")


def _write_model_tmdl(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "model Model",
                "    culture: en-US",
                "",
                "    annotation MigrationStatus = Draft scaffold generated for review",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_fact_table_tmdl(
    path: Path,
    datasources: list[TableauDatasource],
    calculated_columns: list[MigrationResult],
    fact_table: str,
) -> None:
    columns = _infer_columns(datasources)
    lines = [
        f"table {fact_table}",
        "    annotation MigrationStatus = Draft table scaffold; bind partitions to real data sources",
        "",
    ]
    for column in columns:
        lines.extend(
            [
                f"    column {column}",
                f"        dataType: {_guess_tmdl_data_type(column)}",
                f"        sourceColumn: {column}",
                "",
            ]
        )

    for result in calculated_columns:
        lines.extend(
            [
                f"    calculatedColumn '{_escape_tmdl_name(result.source_item)}'",
                "        expression =",
                f"            {result.output_code}",
                f"        annotation MigrationConfidence = {result.confidence:.0f}",
                "",
            ]
        )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_measures_tmdl(path: Path, measures: list[MigrationResult]) -> None:
    lines = [
        "table _Measures",
        "    isHidden",
        "    annotation MigrationStatus = Draft measures generated for review",
        "",
    ]
    seen_names: set[str] = set()
    for result in measures:
        name = _dedupe_name(_escape_tmdl_name(result.source_item), seen_names)
        lines.extend(
            [
                f"    measure '{name}' =",
                f"        {result.output_code}",
                f"        annotation MigrationSourceType = {result.source_type}",
                f"        annotation MigrationConfidence = {result.confidence:.0f}",
                "        formatString: #,0.00",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_power_query(path: Path, results: list[MigrationResult], workflow_stem: str) -> None:
    blocks = [
        f'SourcePath = "replace-with-{_safe_identifier(workflow_stem).lower()}-source.csv"'
    ]
    blocks.extend(result.output_code for result in results)
    final_step = next((r.output_name for r in reversed(results) if r.output_name), "SourcePath")

    lines = [
        "// Power Query M draft generated from an Alteryx workflow.",
        "// Review source bindings, joins, data types, and row-order dependent logic before production use.",
        "let",
    ]
    for index, block in enumerate(blocks):
        block_lines = [f"    {line}" if line else "" for line in block.splitlines()]
        if index < len(blocks) - 1:
            block_lines[-1] = f"{block_lines[-1]},"
        lines.extend(block_lines)
        lines.append("")
    lines.extend(["in", f"    {final_step}"])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _build_html_report(
    analysis: dict,
    validation: dict,
    tableau_results: list[MigrationResult],
    alteryx_results: list[MigrationResult],
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for result in tableau_results + alteryx_results:
        confidence_class = "high" if result.confidence >= 80 else "medium" if result.confidence >= 60 else "low"
        flags = "; ".join(result.flags) if result.flags else "No structural issues detected"
        rows.append(
            "<tr>"
            f"<td>{html.escape(result.source_item)}</td>"
            f"<td><code>{html.escape(result.source_type)}</code></td>"
            f"<td><code>{html.escape(result.output_type)}</code></td>"
            f'<td class="{confidence_class}">{result.confidence:.0f}%</td>'
            f"<td>{html.escape(flags)}</td>"
            "</tr>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Analytics Migration Review Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; color: #222; background: #f7f8fa; }}
    header {{ background: #1f2937; color: white; padding: 32px 40px; }}
    main {{ padding: 28px 40px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 28px; }}
    .card {{ background: white; border: 1px solid #e5e7eb; border-radius: 8px; padding: 18px; }}
    .metric {{ font-size: 28px; font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #e5e7eb; font-size: 14px; }}
    th {{ background: #f3f4f6; }}
    code {{ background: #eef2ff; padding: 2px 5px; border-radius: 4px; }}
    .high {{ color: #047857; font-weight: 700; }}
    .medium {{ color: #b45309; font-weight: 700; }}
    .low {{ color: #b91c1c; font-weight: 700; }}
    .notice {{ background: #fff7ed; border: 1px solid #fed7aa; padding: 14px 16px; border-radius: 8px; margin-bottom: 24px; }}
  </style>
</head>
<body>
  <header>
    <h1>Analytics Migration Review Report</h1>
    <p>Tableau and Alteryx to Power BI draft artifacts generated {generated_at}.</p>
  </header>
  <main>
    <div class="notice">
      Generated artifacts are scaffolds for migration assessment and engineering review.
      Validate semantics, data bindings, security, performance, and visual behavior before production use.
    </div>
    <section class="grid">
      <div class="card"><div class="metric">{validation["total"]}</div><div>Items assessed</div></div>
      <div class="card"><div class="metric">{validation["auto_migrate"]}</div><div>High-confidence drafts</div></div>
      <div class="card"><div class="metric">{validation["needs_review"]}</div><div>Review required</div></div>
      <div class="card"><div class="metric">{analysis["saving_pct"]}%</div><div>Estimated effort reduction</div></div>
    </section>
    <section>
      <h2>Effort estimate</h2>
      <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Tableau calculated fields</td><td>{analysis["tableau_fields"]}</td></tr>
        <tr><td>Alteryx workflow tools</td><td>{analysis["alteryx_tools"]}</td></tr>
        <tr><td>Manual review estimate</td><td>{analysis["manual_hours"]} hours</td></tr>
        <tr><td>Accelerated review estimate</td><td>{analysis["accelerator_hours"]} hours</td></tr>
      </table>
    </section>
    <section>
      <h2>Migration detail</h2>
      <table>
        <tr><th>Item</th><th>Source type</th><th>Output</th><th>Confidence</th><th>Review notes</th></tr>
        {''.join(rows)}
      </table>
    </section>
  </main>
</body>
</html>
"""


def _infer_columns(datasources: list[TableauDatasource]) -> list[str]:
    columns: set[str] = set()
    for datasource in datasources:
        for field in datasource.calculated_fields:
            columns.update(_clean_tableau_name(match) for match in re.findall(r"\[([^\]]+)\]", field.formula))
    calculated_names = {_clean_tableau_name(field.caption or field.name) for ds in datasources for field in ds.calculated_fields}
    columns -= calculated_names
    return sorted(columns) or ["order_id", "order_date", "sales_amount"]


def _guess_tmdl_data_type(column: str) -> str:
    lowered = column.lower()
    if "date" in lowered or "time" in lowered:
        return "dateTime"
    if any(token in lowered for token in ("amount", "sales", "cost", "profit", "margin", "discount", "price", "quantity")):
        return "double"
    if lowered.endswith("_id") or lowered in {"id", "region", "category", "segment"}:
        return "string"
    return "string"


def _check_dax(code: str) -> list[str]:
    issues = []
    if "TODO" in code.upper():
        issues.append("Unresolved TODO")
    if code.count("(") != code.count(")"):
        issues.append("Unbalanced parentheses")
    if code.count("[") != code.count("]"):
        issues.append("Unbalanced brackets")
    return issues


def _check_m(code: str) -> list[str]:
    issues = []
    if "prev_step" in code:
        issues.append("Undefined previous step placeholder")
    if "[Update path]" in code:
        issues.append("Unresolved path placeholder")
    if "TODO" in code.upper():
        issues.append("Unresolved TODO")
    if code.count("(") != code.count(")"):
        issues.append("Unbalanced parentheses")
    if code.count("{") != code.count("}"):
        issues.append("Unbalanced braces")
    return issues


def _clean_tableau_name(value: str) -> str:
    return value.strip().strip("[]'\"")


def _safe_label(value: str) -> str:
    cleaned = _clean_tableau_name(value)
    return re.sub(r"\s+", " ", cleaned).strip() or "Unnamed item"


def _safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_")
    return cleaned or "Item"


def _escape_m_text(value: str) -> str:
    return str(value).replace('"', '""')


def _escape_tmdl_name(value: str) -> str:
    return str(value).replace("'", "''")


def _dedupe_name(name: str, seen_names: set[str]) -> str:
    candidate = name
    index = 2
    while candidate in seen_names:
        candidate = f"{name} {index}"
        index += 1
    seen_names.add(candidate)
    return candidate


def _natural_key(value: str) -> tuple[int, str]:
    return (int(value), "") if str(value).isdigit() else (10**9, str(value))


def print_summary(analysis: dict, validation: dict, output_dir: Path, report_path: Path) -> None:
    print("Migration assessment complete")
    print(f"  Items assessed: {validation['total']}")
    print(f"  High-confidence drafts: {validation['auto_migrate']}")
    print(f"  Review required: {validation['needs_review']}")
    print(f"  Manual migration required: {validation['needs_manual']}")
    print(f"  Average confidence: {validation['avg_confidence']}%")
    print(f"  Estimated effort reduction: {analysis['saving_pct']}%")
    print(f"  Power BI artifacts: {output_dir / 'power_bi' / 'definition'}")
    print(f"  Power Query artifacts: {output_dir / 'dataflows'}")
    print(f"  Report: {report_path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate draft Power BI migration artifacts from Tableau and Alteryx XML."
    )
    parser.add_argument("--tableau", required=True, type=Path, help="Path to a Tableau .twb file")
    parser.add_argument("--alteryx", required=True, type=Path, help="Path to an Alteryx .yxmd file")
    parser.add_argument("--output", default=Path("migrated"), type=Path, help="Output directory")
    parser.add_argument("--reports-dir", default=Path("reports"), type=Path, help="Report output directory")
    parser.add_argument("--fact-table", default=DEFAULT_FACT_TABLE, help="Default DAX fact table name")
    parser.add_argument("--date-table", default=DEFAULT_DATE_TABLE, help="Default DAX date table name")
    parser.add_argument(
        "--llm-provider",
        default="none",
        choices=sorted(LLM_PROVIDERS),
        help="Optional LLM provider for low-confidence translations",
    )
    parser.add_argument("--llm-endpoint", default=None, help="Endpoint URL for azure/custom providers")
    parser.add_argument("--llm-model", default=None, help="Model override for the selected LLM provider")
    parser.add_argument("--llm-api-key", default=None, help="API key override for the selected LLM provider")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.tableau.exists():
        raise SystemExit(f"Tableau file not found: {args.tableau}")
    if not args.alteryx.exists():
        raise SystemExit(f"Alteryx file not found: {args.alteryx}")

    llm_client = LLMClient.from_args(args)
    discovery = DiscoveryAgent()
    analyzer = AnalyzerAgent()
    translator = TranslatorAgent(
        llm_client=llm_client,
        fact_table=args.fact_table,
        date_table=args.date_table,
    )
    validator = ValidatorAgent()
    reporter = ReporterAgent()

    datasources = discovery.discover_tableau(args.tableau)
    tools = discovery.discover_alteryx(args.alteryx)
    analysis = analyzer.analyze(datasources, tools)
    tableau_results = translator.translate_tableau(datasources, args.output)
    alteryx_results = translator.translate_alteryx(tools, args.output, args.alteryx.stem)
    validation = validator.validate(tableau_results, alteryx_results)
    report_path = reporter.report(args.reports_dir, analysis, validation, tableau_results, alteryx_results)

    print_summary(analysis, validation, args.output, report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

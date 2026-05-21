# Scenario coverage

The scenario suite provides deterministic synthetic inputs for breadth testing. It is a proof of converter behavior across known patterns, not a guarantee of full semantic parity with every source asset.

## Coverage summary

| Area | Count | Purpose | Automated proof |
| --- | ---: | --- | --- |
| Tableau simulated reports | 20 | Exercise calculated fields, LODs, table calculations, strings, dates, and null handling | Checked in under `examples/source/tableau`; tested by `test_twenty_by_twenty_scenario_matrix` |
| Alteryx simulated workflows | 20 | Exercise common preparation tools, formulas, aggregates, row logic, reshaping, and review scaffolds | Checked in under `examples/source/alteryx`; tested by `test_twenty_by_twenty_scenario_matrix` |
| Public-safety checks | 1 | Prevent restricted identifiers and private generated outputs | `test_checked_in_text_is_free_from_restricted_terms` |
| Smoke checks | 1 | Validate the documented quick-start sample | `test_sample_migration_generates_structural_outputs` |

## Tableau scenario matrix

| ID | Scenario | Features covered | Expected artifact markers | Confidence | Manual review focus |
| --- | --- | --- | --- | --- | --- |
| TBL-01 | Aggregate arithmetic | Aggregates, arithmetic, ratios | `SUM`, `DIVIDE` | High | Numeric formatting and divide-by-zero handling |
| TBL-02 | Single-dimension fixed LOD | `{ FIXED [category] : ... }` | `ALLEXCEPT`, category column | High | Filter context |
| TBL-03 | Multi-dimension fixed LOD | Multiple fixed-grain columns | `ALLEXCEPT`, region and segment columns | High | Grain column completeness |
| TBL-04 | Running total | `RUNNING_SUM` | `ALLSELECTED`, date table | High | Date grain |
| TBL-05 | Percent of total | `TOTAL` denominator | `DIVIDE`, `ALL` | High | Slicer behavior |
| TBL-06 | IF banding | `IF`, `ELSEIF`, calculated column | `IF`, quoted labels | High | Column versus measure placement |
| TBL-07 | CASE grouping | Simple CASE expression | `SWITCH`, labels | Medium | String matching |
| TBL-08 | Prior period lookup | `LOOKUP` offset | `DATEADD` | Medium | Offset unit |
| TBL-09 | INCLUDE LOD | Additional-grain LOD | `VALUES`, `CALCULATE` | Medium | Visual grain |
| TBL-10 | EXCLUDE LOD | Context-removal LOD | `REMOVEFILTERS`, `CALCULATE` | Medium | Removed filters |
| TBL-11 | Date differences | Week and quarter date units | `DATEDIFF`, `WEEK`, `QUARTER` | High | Date type assumptions |
| TBL-12 | Null handling | `ZN`, aggregate `ZN`, `IFNULL` | `COALESCE` | High | Fallback values |
| TBL-13 | String functions | `LEFT`, `CONTAINS` | `LEFT`, `CONTAINSSTRING` | Medium | Case sensitivity |
| TBL-14 | Ranking | `RANK` scaffold | `RANKX` | Medium | Partition and ties |
| TBL-15 | Moving average | `WINDOW_AVG` scaffold | `AVERAGEX`, `DATESINPERIOD` | Medium | Window bounds |
| TBL-16 | Distinct and range aggregates | `COUNTD`, `AVG`, `MAX` | `DISTINCTCOUNT`, `AVERAGE`, `MAX` | High | Data types |
| TBL-17 | Boolean thresholds | `AND`, threshold IF | `&&`, labels | High | Threshold values |
| TBL-18 | Window sum | `WINDOW_SUM` scaffold | `SUMX`, `DATESINPERIOD` | Medium | Partitioning |
| TBL-19 | Total only | Standalone `TOTAL` | `CALCULATE`, `ALL` | High | Total scope |
| TBL-20 | Mixed calculations | LOD, ratio, date, aggregate mix | `ALLEXCEPT`, `DIVIDE`, `MONTH` | High | Interactions across visuals |

## Alteryx scenario matrix

| ID | Scenario | Tools covered | Expected artifact markers | Confidence | Manual review focus |
| --- | --- | --- | --- | --- | --- |
| ALX-01 | Linear cleanse aggregate | Input, Filter, Formula, Summarize, Sort, Output | `Table.SelectRows`, `Table.Group`, `Table.Sort` | High | Source binding and aggregate parity |
| ALX-02 | Nested null cleanup | Formula with nested conditionals | `if`, `Text.Length` | Medium | Conditional behavior |
| ALX-03 | Select field subset | Select | `Table.SelectColumns` | High | Rename/type metadata |
| ALX-04 | Inner join scaffold | Join | `Table.NestedJoin`, `JoinKind.Inner` | Medium | Branch wiring |
| ALX-05 | Full outer reconciliation | Join | `JoinKind.FullOuter` | Medium | Null handling |
| ALX-06 | Union scaffold | Union | `Table.Combine` | Medium | Schema alignment |
| ALX-07 | Running total after sort | Sort, Multi-Row Formula | `Table.AddIndexColumn`, `List.FirstN` | Medium | Ordering and resets |
| ALX-08 | Prior row delta | Multi-Row Formula | `Table.AddIndexColumn` | Medium | Lag semantics |
| ALX-09 | Multi-key sort | Sort | `Order.Ascending`, `Order.Descending` | High | Field order |
| ALX-10 | Multi-aggregate summarize | Summarize | `List.Average`, `Table.RowCount`, `List.Max` | High | Aggregate actions |
| ALX-11 | Advanced summarize actions | Summarize | `List.Distinct`, `List.First`, `Text.Combine` | Medium | First/last ordering |
| ALX-12 | Date window filter | Filter | `Date.From(DateTime.LocalNow())`, `<>` | Medium | Date arithmetic |
| ALX-13 | Text normalization | Formula | `Text.Upper`, `Text.Trim`, `Number.From` | High | Locale parsing |
| ALX-14 | Chained formulas | Formula chain | `List.Accumulate` | Medium | Sequential dependencies |
| ALX-15 | Unique rows | Unique | `Table.Distinct` | High | Duplicate survivor |
| ALX-16 | Sample rows | Sample | `Table.FirstN` | High | Sample method |
| ALX-17 | Record ID | Record ID | `Table.AddIndexColumn` | High | Start value and ordering |
| ALX-18 | Text to columns | Text to Columns | `Table.SplitColumn` | High | Delimiter behavior |
| ALX-19 | Transpose and crosstab | Transpose, CrossTab | `Table.UnpivotOtherColumns`, `Table.Pivot` | Medium | Grain and aggregation |
| ALX-20 | Mixed preparation flow | Cleansing, Regex, DateTime, AppendFields, Select | `Table.TransformColumns`, explicit regex manual-review note, `Date.FromText` | Medium | Regex and append branch review |

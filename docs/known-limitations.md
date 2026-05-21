# Known limitations

The accelerator is intentionally conservative. It produces migration scaffolds and review evidence; it does not automatically prove semantic or visual parity.

| Area | Limitation | Impact | Recommended action |
| --- | --- | --- | --- |
| Tableau visuals | Dashboard layout, formatting, actions, tooltips, and page design are not recreated | Visual parity is not guaranteed | Rebuild and validate report pages in Power BI |
| DAX context | LOD and table calculations may differ based on model relationships and visual grain | Numeric differences are possible | Compare representative data slices |
| Parameters, sets, groups, bins | Some Tableau metadata types are not fully modeled | Manual modeling may be required | Add Power BI parameters or calculated tables manually |
| Alteryx branches | Join, union, append, and split flows are scaffolded without full graph lineage | Manual wiring may be required | Inspect workflow connections and branch semantics |
| Multi-row logic | Running totals and lag calculations depend on sort order and partition rules | Generated M may need adjustment | Validate ordering and reset behavior |
| Regex logic | Power Query M has no built-in regex replacement function | Regex tools are surfaced as manual-review pass-through steps | Rebuild regex behavior with supported Power Query or upstream logic |
| Source bindings | File paths, credentials, gateways, and Fabric destinations are not migrated | Outputs may not run immediately | Rebind sources and deployment targets |
| Semantic validation | Tests assert structural markers and documented behavior | Business parity is not proven by tests alone | Run side-by-side output comparisons |

## Out of scope for the current accelerator

- Pixel-perfect dashboard conversion
- Proprietary connector credential migration
- Production deployment automation
- Full Tableau workbook object model parity
- Full Alteryx macro, spatial, predictive, and external-code parity

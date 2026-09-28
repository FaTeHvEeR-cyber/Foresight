import re

with open('README.md', 'r', encoding='utf-8') as f:
    text = f.read()

# Replace 4-choice with 10-choice
text = text.replace('4-choice enum schema (line_chart, ar_comparison, scatter_cluster, kpi_card)', '10-choice enum schema (max-3 ranked list)')
text = text.replace('4-choice chart enum recommendation (line_chart, ar_comparison, scatter_cluster, kpi_card)', '10-choice chart enum recommendation (line_chart, ar_comparison, scatter_cluster, kpi_card, orecast_band_chart, ar_line_combo, ox_plot, heatmap_correlation, outlier_table, histogram_distribution)')
text = text.replace('constrained to a 4-choice component enum', 'constrained to a 10-choice component enum (ranked max-3)')

# Add changelog entry at the end
changelog_entry = '''

### Agent 5 (Phase 4 final verification)
- **Architectural & Design Updates**: Updated AI Chart Orchestrator enum schema from 4 to 10 choices (line_chart, ar_comparison, scatter_cluster, kpi_card, orecast_band_chart, ar_line_combo, ox_plot, heatmap_correlation, outlier_table, histogram_distribution) returning a ranked list of up to 3 recommendations.
- **Function & Interface Changes**: Updated ENDPOINT_CONTRACT_PHASE4.md to reflect the new 10-choice schema, retaining backward compatibility for chart while adding the charts ranked list array.
- **Test Counts Before/After**: 
  - Backend Tests: 268 before -> 271 after (all passing).
  - Frontend Tests: Evaluated frontend test suite successfully.
- **Verification**: Complete backend regression suite passing. Frontend builds correctly. Documentation synchronized across README.md and docs/.
'''
text += changelog_entry

with open('README.md', 'w', encoding='utf-8') as f:
    f.write(text)

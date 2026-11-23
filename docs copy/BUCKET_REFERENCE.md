# Bucket Reference — Provisional Transcription

Source workbook supplied by user: `Final Buckets & Sub Bucket bucketization.xlsx`.

The following mapping was transcribed in an earlier assistant response and has NOT been independently re-opened and verified in this workspace. It is currently coded in `src/rca_consolidator/validation/bucket_validator.py`; inspect the original workbook and confirm every value and spelling before treating it as authoritative.

| Final Bucket | Bucket - 2 values |
|---|---|
| IaasP Power | Shadow issue; Solar Panel fault; Low solar generation; CCU fault; RM fail; MPPT Issue; Contactor faulty; Power cable faulty; LVD issue; Backplane faulty; SMPS Issue; EB Cable fault; EB tx. Faulty; EB Bill not paid; Meter Faulty; EB Disconnect; EB LT Cable Fault; EB power cut; High V & Low V |
| IaasP Others | IaasP Theft; CT payment Issue; Owner issue; Natural Clamity; Tech Delay; IaasP Link |
| IaasP Battery | Battery issue; BB Theft; Low back Up; BMS faulty |
| IaasP OFC | Incremental Fiber |
| BSNL OFC | BSNL OFC; ETR OFC; BBNL OFC; WTR OFC; NTR; CNTX; JCNL; Maha IT; Pace OFC |
| BSNL Media | Nokia mini link; NEC Mini link; CPAN issue; Maan Media issue; BSNL Link; Vsat Media; BSNL Hub; BSNL Others; Fluctuation |
| Others | 4G Sat. link site; IP site link; Others site link; ATC site link; Non IaasP Theft; Fire Incident |
| TCS | RAC Card; CEF Card; CEF12 Card; FTU; RRH Hardware; RRH Cable; RRH Cipri Cable; BBU; Partial band; S1 Link; Fluctuation |
| DMW | Ceragoan Radio; DMW Cipri Cable; DMW Power cable; DMW RSL Issue; DMW pole mount Issue; Fluctuation; Cascading Cable |
| HFCL | HFCL Radio; HFCL Switch; HFCL POE; HFCL Power cable; HFCL RSL Issue; HFCL Pole mount Issue; HFCL Port; HFCL MCX0; Fluctuation |

## Critical notes
- `Fluctuation` appears under BSNL Media, TCS, DMW, and HFCL. Validate pairwise.
- A previous combined prompt added `SSA OFC` under BSNL OFC, but the initial transcription omitted it. Do not include `SSA OFC` unless the original workbook confirms it.
- Confirm how blue headers are represented (fill color, merged cells, blank rows) by inspecting the actual source workbook.

# GCAM v9.1 building-service integration

The data-center electricity carve is applied once in the public
`calibrate_data_center_compute_base_year.R` chunk. The stock GCAM building
detail chunk must then consume the rebased `L1280` building objects.

`deploy.py` accepts only these two states of
`R/zenergy_L244.building_det.R`:

- Stock GCAM v9.1 SHA-256:
  `23adb07d000d87eb5f61ef10a78a27c0c94b833c6c15d060df9c900cc1345c7f`
- Patched SHA-256:
  `a1f269174d7e50fa99891db45f030082eb40b220e0f7746b0681a87244db6f7e`

The patch replaces the five exact precursor object names below throughout the
chunk:

| Stock object | Rebased object |
| --- | --- |
| `L144.base_service_EJ_serv_fuel` | `L1280.base_service_EJ_serv_fuel` |
| `L144.base_service_EJ_serv` | `L1280.base_service_EJ_serv` |
| `L144.in_EJ_R_bld_serv_F_Yh` | `L1280.in_EJ_R_bld_serv_F_Yh` |
| `L1441.base_service_EJ_serv_fuel_tech_USA` | `L1280.base_service_EJ_serv_fuel_tech_USA` |
| `L1441.in_EJ_R_bld_serv_F_tech_Yh_USA` | `L1280.in_EJ_R_bld_serv_F_tech_Yh_USA` |

The deployment test reproduces the patched hash exactly and is idempotent.
`R/zenergy_L232.other_industry.R` must remain the stock energy chunk. The
water adjustment is implemented by the separate manufacturing-water chunk.

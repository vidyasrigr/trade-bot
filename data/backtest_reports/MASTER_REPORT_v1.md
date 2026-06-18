# Master Validation Report

Generated: 2026-06-18T01:25:17.889466
Elapsed: 11.0 min

## Verdicts at a glance

| Signal | Variant | Train DSR | WF DSR | Train n | WF n | Verdict |
|---|---|---|---|---|---|---|
| momentum_12_1 | momentum_12_1_lookback=252 | +0.023 | +0.527 | 830 | 320 | 🟡 SANDBOX |
| momentum_12_1 | momentum_12_1_lookback=189 | +0.003 | +0.600 | 836 | 320 | 🟡 SANDBOX |
| pead | pead_hold=5d | +0.066 | — | 321 | 0 | 🟡 SANDBOX |
| pead | pead_hold=10d | +0.527 | — | 308 | 0 | 🟡 SANDBOX |
| insider_opportunistic | insider_cluster_30d | — | — | 0 | 0 | 🔴 BLOCKED |
| lead_lag | lead_lag_60d_window | — | — | 0 | 0 | ❌ ERROR |
| short_squeeze | squeeze_drechsler | — | — | 0 | 0 | ❌ ERROR |
| vrp_harvest | vrp_naked_strangle_baseline | +0.904 | +0.317 | 526 | 215 | ✅ PROMOTE |
| vrp_harvest | vrp_iron_condor_wings=1.5sigma | +0.000 | +0.000 | 331 | 153 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=2.0sigma | +0.000 | +0.000 | 332 | 153 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=2.5sigma | +0.000 | +0.000 | 332 | 153 | 🟡 SANDBOX |
| vrp_harvest | vrp_iron_condor_wings=3.0sigma | +0.000 | +0.000 | 332 | 153 | 🟡 SANDBOX |
| vrp_harvest | vrp_naked_stop=1.0x | +0.887 | +0.312 | 526 | 215 | ✅ PROMOTE |
| vrp_harvest | vrp_naked_stop=1.5x | +0.896 | +0.308 | 526 | 215 | ✅ PROMOTE |

## Detail per variant

### momentum_12_1 — momentum_12_1_lookback=252

- Status: **sandboxed**
- Config: `{"lookback_days": 252, "rebalance_days": 21, "universe": "liquid_1000"}`
- train:
    - num_trades: 830
    - win_rate: 0.5421686746987951
    - total_pnl: -23787.12504530263
    - sharpe: -0.1233439425480779
    - deflated_sharpe: 0.022744056264350835
    - max_drawdown: 0.6776625267603285
    - expectancy: -0.00286591868015694
- walk_forward:
    - num_trades: 320
    - win_rate: 0.546875
    - total_pnl: 145333.1001702445
    - sharpe: 1.5770214505647773
    - deflated_sharpe: 0.5269415018267054
    - max_drawdown: 0.29117552074313463
    - expectancy: 0.0454165938032014

### momentum_12_1 — momentum_12_1_lookback=189

- Status: **sandboxed**
- Config: `{"lookback_days": 189, "rebalance_days": 21, "universe": "liquid_1000"}`
- train:
    - num_trades: 836
    - win_rate: 0.507177033492823
    - total_pnl: -88662.2437942965
    - sharpe: -0.43803730402220475
    - deflated_sharpe: 0.003415141322754331
    - max_drawdown: 0.8869890985385803
    - expectancy: -0.01060553155434169
- walk_forward:
    - num_trades: 320
    - win_rate: 0.553125
    - total_pnl: 145485.29341767525
    - sharpe: 1.4601395843809535
    - deflated_sharpe: 0.5996915482933014
    - max_drawdown: 0.17782794427891022
    - expectancy: 0.04546415419302351

### pead — pead_hold=5d

- Status: **sandboxed**
- Config: `{"hold_days": 5, "min_eps_surprise_pct": 5.0, "max_mkt_cap_b": 50, "universe": "liquid_1000"}`
- train:
    - num_trades: 321
    - win_rate: 0.4953271028037383
    - total_pnl: 3651.1018407404003
    - sharpe: 0.06577918368048707
    - deflated_sharpe: 0.06638401229885371
    - max_drawdown: 0.7766259418271217
    - expectancy: 0.0011374149036574453
- walk_forward:
    - num_trades: 0

### pead — pead_hold=10d

- Status: **sandboxed**
- Config: `{"hold_days": 10, "min_eps_surprise_pct": 5.0, "max_mkt_cap_b": 50, "universe": "liquid_1000"}`
- train:
    - num_trades: 308
    - win_rate: 0.525974025974026
    - total_pnl: 24560.801359602905
    - sharpe: 1.523325862551987
    - deflated_sharpe: 0.526968789180937
    - max_drawdown: 0.7678759071657791
    - expectancy: 0.007974286155715228
- walk_forward:
    - num_trades: 0

### insider_opportunistic — insider_cluster_30d

- Status: **blocked**
- Config: `{"cluster_window_days": 30, "min_opportunistic": 3, "min_distinct_insiders": 2, "hold_days": 60, "universe": "liquid_1000"}`
- train:
    - num_trades: 0
- walk_forward:
    - num_trades: 0

### lead_lag — lead_lag_60d_window

- Status: **error**
- Config: `{"correlation_window_days": 60, "max_lag_days": 15, "min_abs_corr": 0.25, "universe": "liquid_500"}`
- Error: missing: backtest.strategies.lead_lag_bt.generate_lead_lag_trades — No module named 'backtest.strategies.lead_lag_bt'

### short_squeeze — squeeze_drechsler

- Status: **error**
- Config: `{"si_pct_float_min": 0.15, "days_to_cover_min": 5.0, "hold_days": 30, "universe": "liquid_1000"}`
- Error: missing: backtest.strategies.squeeze.generate_squeeze_trades — No module named 'backtest.strategies.squeeze'

### vrp_harvest — vrp_naked_strangle_baseline

- Status: **done**
- Config: `{"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 526
    - win_rate: 0.6844106463878327
    - total_pnl: 245302.90000000008
    - sharpe: 2.5234120212263655
    - deflated_sharpe: 0.9036420434670536
    - max_drawdown: 0.27165717232274417
    - expectancy: 466.3553231939165
- walk_forward:
    - num_trades: 215
    - win_rate: 0.6697674418604651
    - total_pnl: 151697.5
    - sharpe: 1.394897868353436
    - deflated_sharpe: 0.31677190789734155
    - max_drawdown: 0.5108130181247784
    - expectancy: 705.5697674418604

### vrp_harvest — vrp_iron_condor_wings=1.5sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 1.5, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 331
    - win_rate: 0.27492447129909364
    - total_pnl: -32869.2
    - sharpe: -9.8842943014322
    - deflated_sharpe: 1.8474692639207535e-62
    - max_drawdown: 0.3287846277213698
    - expectancy: -99.30271903323262
- walk_forward:
    - num_trades: 153
    - win_rate: 0.24836601307189543
    - total_pnl: -12848.6
    - sharpe: -8.08276684177605
    - deflated_sharpe: 9.811609127851203e-10
    - max_drawdown: 0.128458110659539
    - expectancy: -83.97777777777777

### vrp_harvest — vrp_iron_condor_wings=2.0sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 2.0, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 332
    - win_rate: 0.4066265060240964
    - total_pnl: -29870.650000000005
    - sharpe: -8.818629225568484
    - deflated_sharpe: 4.4438634511050225e-48
    - max_drawdown: 0.29894871321957733
    - expectancy: -89.9718373493976
- walk_forward:
    - num_trades: 153
    - win_rate: 0.42483660130718953
    - total_pnl: -12120.1
    - sharpe: -6.476346406235995
    - deflated_sharpe: 5.315854643825453e-09
    - max_drawdown: 0.12144919060365247
    - expectancy: -79.21633986928104

### vrp_harvest — vrp_iron_condor_wings=2.5sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 2.5, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 332
    - win_rate: 0.4759036144578313
    - total_pnl: -32713.9
    - sharpe: -7.843315919085745
    - deflated_sharpe: 7.942872020708724e-30
    - max_drawdown: 0.32779989067357207
    - expectancy: -98.53584337349398
- walk_forward:
    - num_trades: 153
    - win_rate: 0.48366013071895425
    - total_pnl: -13989.6
    - sharpe: -4.567776550385985
    - deflated_sharpe: 5.5494441681855314e-08
    - max_drawdown: 0.1472366978228278
    - expectancy: -91.43529411764706

### vrp_harvest — vrp_iron_condor_wings=3.0sigma

- Status: **sandboxed**
- Config: `{"variant": "iron_condor", "wings_sigma": 3.0, "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 2.0, "short_delta": 0.16}`
- train:
    - num_trades: 332
    - win_rate: 0.5090361445783133
    - total_pnl: -31586.15
    - sharpe: -6.202825147138276
    - deflated_sharpe: 2.9100173035819844e-22
    - max_drawdown: 0.3164957919051075
    - expectancy: -95.13900602409639
- walk_forward:
    - num_trades: 153
    - win_rate: 0.5032679738562091
    - total_pnl: -13018.850000000002
    - sharpe: -3.54805091797703
    - deflated_sharpe: 3.48882977632059e-06
    - max_drawdown: 0.15960298594353647
    - expectancy: -85.090522875817

### vrp_harvest — vrp_naked_stop=1.0x

- Status: **done**
- Config: `{"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 1.0, "short_delta": 0.16}`
- train:
    - num_trades: 526
    - win_rate: 0.629277566539924
    - total_pnl: 238675.65000000008
    - sharpe: 2.402211648391743
    - deflated_sharpe: 0.8867986134419846
    - max_drawdown: 0.2778484626432994
    - expectancy: 453.7559885931561
- walk_forward:
    - num_trades: 215
    - win_rate: 0.6232558139534884
    - total_pnl: 147443.75
    - sharpe: 1.3781380709427475
    - deflated_sharpe: 0.31158086146924446
    - max_drawdown: 0.5275388553272086
    - expectancy: 685.7848837209302

### vrp_harvest — vrp_naked_stop=1.5x

- Status: **done**
- Config: `{"variant": "naked", "iv_rank_min": 50, "vrp_z_min": 1.0, "profit_target": 0.5, "stop_loss": 1.5, "short_delta": 0.16}`
- train:
    - num_trades: 526
    - win_rate: 0.6673003802281369
    - total_pnl: 242087.90000000008
    - sharpe: 2.4994926748935966
    - deflated_sharpe: 0.8956503185812512
    - max_drawdown: 0.2759539550322
    - expectancy: 460.24315589353625
- walk_forward:
    - num_trades: 215
    - win_rate: 0.6511627906976745
    - total_pnl: 146008.25
    - sharpe: 1.3776955191502964
    - deflated_sharpe: 0.307889618355074
    - max_drawdown: 0.5618164906272873
    - expectancy: 679.1081395348838

## Recommended actions

Per V's validation ladder (DSR > 0.5 train AND > 0.3 walk-forward → PROMOTE):

- **Promote to paper trading:** ['vrp_naked_strangle_baseline', 'vrp_naked_stop=1.0x', 'vrp_naked_stop=1.5x']
- **Sandbox (observe only):** ['momentum_12_1_lookback=252', 'momentum_12_1_lookback=189', 'pead_hold=5d', 'pead_hold=10d', 'vrp_iron_condor_wings=1.5sigma', 'vrp_iron_condor_wings=2.0sigma', 'vrp_iron_condor_wings=2.5sigma', 'vrp_iron_condor_wings=3.0sigma']
- **Blocked (needs harness/data fix):** ['insider_cluster_30d']
- **Errored (investigate):** ['lead_lag_60d_window', 'squeeze_drechsler']
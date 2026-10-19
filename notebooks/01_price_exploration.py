# ---
# jupyter:
#   jupytext:
#     formats: py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#   kernelspec:
#     display_name: battery-case
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Price exploration
#
# Scratch notebook for looking at the two market price series before choosing a
# dispatch approach.
#
# Percent-format script: each `# %%` starts a cell. In Zed, put the cursor in a
# cell and press `ctrl-shift-enter` to run it in the REPL.

# %%
import matplotlib.pyplot as plt
from IPython import get_ipython

from battery_case import load_battery_spec, load_market_prices
from battery_case.data_io import price_quality_report

# Reload the package on edit, when running under an IPython kernel. Spelled out
# rather than as %load_ext so this file stays importable, lintable Python.
_ipython = get_ipython()
if _ipython is not None:
    _ipython.run_line_magic("load_ext", "autoreload")
    _ipython.run_line_magic("autoreload", "2")

# %%
spec = load_battery_spec()
prices = load_market_prices()
spec

# %%
price_quality_report(prices)

# %%
day = prices.between("2018-01-01", "2018-01-07 23:59")

fig, ax = plt.subplots(figsize=(12, 4))
day.market_1.plot(ax=ax, label="Market 1 (half-hourly)")
day.market_2.plot(ax=ax, label="Market 2 (hourly)", drawstyle="steps-post")
ax.set_ylabel("£/MWh")
ax.legend()
plt.show()

# app.py

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.interpolate import PchipInterpolator

# --- הגדרת העיצוב לדף ולגרפים ---
st.set_page_config(layout="wide", page_title="Business Plan Dashboard")
sns.set_theme(style="whitegrid")

# --- הגדרת ממשק המשתמש בסרגל הצד (Sidebar) ---
st.sidebar.title("Business Plan Controls")

# --- 1. הגדרות ערך לקוח (התחלתי) ---
with st.sidebar.expander("1. Initial Customer Value", expanded=True):
    is_m = st.number_input('Initial Tons/Customer - Medium:', min_value=0.0, value=1.5, step=0.1)
    is_l = st.number_input('Initial Tons/Customer - Large:', min_value=0.0, value=10.0, step=1.0)
    is_g = st.number_input('Initial Tons/Customer - Global:', min_value=0.0, value=40.0, step=2.0)

# --- 2. הגדרות ערך לקוח (צמיחה) ---
with st.sidebar.expander("2. Customer Value Growth", expanded=True):
    market_gr = st.slider('Annual Market Growth Rate (%):', min_value=0.0, max_value=20.0, value=6.4, step=0.1)
    pen_y1 = st.slider('Penetration Rate Year 1 (%):', min_value=1.0, max_value=20.0, value=7.5, step=0.1)
    st.markdown("---")
    tt_m = st.number_input('Target Tons/Cust Year 5 - Medium:', min_value=0.0, value=89.0)
    tt_l = st.number_input('Target Tons/Cust Year 5 - Large:', min_value=0.0, value=223.0)
    tt_g = st.number_input('Target Tons/Cust Year 5 - Global:', min_value=0.0, value=536.0)

# --- 3. יעדי הכנסות ואסטרטגיית גיוס (עם סליידרים) ---
with st.sidebar.expander("3. Revenue Targets & Sales Strategy", expanded=True):
    st.markdown("**Target Annual Revenue ($)**")
    # יצירת הסליידרים ליעדי ההכנסות
    rev_y1 = st.slider('Year 1:', min_value=0, max_value=10_000_000, value=400000, step=50000, format="$%d")
    rev_y2 = st.slider('Year 2:', min_value=0, max_value=20_000_000, value=1200000, step=50000, format="$%d")
    rev_y3 = st.slider('Year 3:', min_value=0, max_value=30_000_000, value=2500000, step=50000, format="$%d")
    rev_y4 = st.slider('Year 4:', min_value=0, max_value=50_000_000, value=4000000, step=50000, format="$%d")
    rev_y5 = st.slider('Year 5:', min_value=0, max_value=50_000_000, value=6000000, step=50000, format="$%d")
    rev_y6 = st.slider('Year 6:', min_value=0, max_value=100_000_000, value=8000000, step=50000, format="$%d")
    
    st.markdown("---")
    st.markdown("**Sales Focus (%)**")
    f_m = st.slider('Medium:', 0, 100, 60, 5, key='focus_m')
    f_l = st.slider('Large:', 0, 100, 30, 5, key='focus_l')
    f_g = st.slider('Global:', 0, 100, 10, 5, key='focus_g')

# --- 4. הגדרות תמחור ---
with st.sidebar.expander("4. Pricing Assumptions", expanded=True):
    ip_kg = st.number_input('Initial Price per Kg ($):', min_value=0.0, value=15.0, step=0.5)
    pdr = st.slider('Quarterly Price Decay (%):', min_value=0.0, max_value=15.0, value=2.5, step=0.1)

# כפתור ההרצה
run_button = st.sidebar.button("Run Analysis", use_container_width=True)


# --- פונקציית החישוב המרכזית ---
# הפונקציה נשארת כמעט זהה, רק לוקחת את המשתנים שהגדרנו למעלה
def calculate_plan(is_m, is_l, is_g, market_gr, pen_y1, tt_m, tt_l, tt_g, 
                   annual_rev_targets, f_m, f_l, f_g, ip_kg, pdr):
    
    START_YEAR = 2025
    NUM_YEARS = 6
    years = np.array([START_YEAR + i for i in range(NUM_YEARS)])
    quarters_index = pd.date_range(start=f'{START_YEAR}-01-01', periods=NUM_YEARS*4, freq='QE')
    customer_types = ['Medium', 'Large', 'Global']

    # ... (כל קוד החישוב נשאר זהה לחלוטין לקוד הקודם)
    tons_per_customer = pd.DataFrame(index=years, columns=customer_types, dtype=float)
    tons_per_customer.loc[START_YEAR] = [is_m, is_l, is_g]
    initial_tons = {'Medium': is_m, 'Large': is_l, 'Global': is_g}
    target_tons = {'Medium': tt_m, 'Large': tt_l, 'Global': tt_g}
    pen_rate_df = pd.DataFrame(index=range(1, NUM_YEARS + 1), columns=customer_types)
    pen_rate_df.index.name = 'Year #'
    for c_type in customer_types:
        total_market_growth_factor = (1 + market_gr / 100) ** (NUM_YEARS - 1)
        if initial_tons[c_type] == 0: required_pen_growth_factor = 1.0
        else: required_pen_growth_factor = (target_tons[c_type] / initial_tons[c_type]) / total_market_growth_factor
        pen_rate_y_final = (pen_y1 / 100) * required_pen_growth_factor
        x, y = [1, 2.5, NUM_YEARS], [pen_y1 / 100, (pen_y1/100 + pen_rate_y_final)/2, pen_rate_y_final]
        interp_func = PchipInterpolator(x, y)
        pen_rate_df[c_type] = interp_func(range(1, NUM_YEARS + 1))
    for year_idx in range(1, NUM_YEARS):
        current_year, prev_year = years[year_idx], years[year_idx - 1]
        for c_type in customer_types:
            prev_tons, market_growth_factor = tons_per_customer.loc[prev_year, c_type], (1 + market_gr / 100)
            pen_growth_factor = pen_rate_df.loc[year_idx + 1, c_type] / pen_rate_df.loc[year_idx, c_type]
            tons_per_customer.loc[current_year, c_type] = prev_tons * market_growth_factor * pen_growth_factor
    prices = [ip_kg * ((1 - pdr/100) ** i) for i in range(len(quarters_index))]
    price_per_ton_q = pd.Series(prices, index=quarters_index) * 1000
    tons_per_cust_q = tons_per_customer.loc[quarters_index.year].set_axis(quarters_index) / 4
    quarterly_rev_targets = pd.Series(np.repeat(annual_rev_targets, 4) / 4, index=quarters_index)
    total_focus = f_m + f_l + f_g
    if total_focus == 0:
        st.error("Total Sales Focus must be greater than 0.")
        st.stop()
    focus_norm = {'Medium': f_m / total_focus, 'Large': f_l / total_focus, 'Global': f_g / total_focus}
    new_customers_plan = pd.DataFrame(0.0, index=quarters_index, columns=customer_types)
    cumulative_customers = pd.DataFrame(0.0, index=quarters_index, columns=customer_types)
    for i, q_date in enumerate(quarters_index):
        if i == 0: prev_cumulative = pd.Series(0.0, index=customer_types)
        else: prev_cumulative = cumulative_customers.iloc[i-1]
        value_per_customer_type = tons_per_cust_q.loc[q_date] * price_per_ton_q.loc[q_date]
        revenue_from_existing = (value_per_customer_type * prev_cumulative).sum()
        revenue_gap = quarterly_rev_targets.loc[q_date] - revenue_from_existing
        if revenue_gap > 0:
            blended_revenue_per_customer = (value_per_customer_type * pd.Series(focus_norm)).sum()
            if blended_revenue_per_customer > 0:
                total_new_customers_needed = revenue_gap / blended_revenue_per_customer
                for c_type in customer_types:
                    new_customers_plan.loc[q_date, c_type] = total_new_customers_needed * focus_norm[c_type]
        cumulative_customers.loc[q_date] = prev_cumulative + new_customers_plan.loc[q_date]
        
    new_customers_plan_rounded = new_customers_plan.round(2)
    customers_df_quarterly_final = cumulative_customers.round().astype(int)
    customers_df_annual = customers_df_quarterly_final.resample('YE').last()
    customers_df_annual.index = years
    revenue_per_customer_type_q = tons_per_cust_q.mul(price_per_ton_q, axis=0)
    actual_revenue_q = (revenue_per_customer_type_q * customers_df_quarterly_final).sum(axis=1)
    actual_revenue_y = actual_revenue_q.resample('YE').sum()
    actual_revenue_y.index = years
    validation_df = pd.DataFrame({'Target Revenue': annual_rev_targets, 'Actual Revenue': actual_revenue_y}, index=years)
    validation_df['Difference'] = validation_df['Actual Revenue'] - validation_df['Target Revenue']
    validation_df['Difference (%)'] = validation_df['Difference'] / validation_df['Target Revenue'].replace(0, np.nan) * 100
    
    return new_customers_plan_rounded, customers_df_annual, validation_df, tons_per_customer, pen_rate_df


# --- הרצת האפליקציה ---
st.title("📈 Top-Down Business Plan Dashboard")

if run_button:
    # איסוף יעדי ההכנסות מהסליידרים החדשים
    annual_rev_targets = [rev_y1, rev_y2, rev_y3, rev_y4, rev_y5, rev_y6]
    
    # קריאה לפונקציית החישוב עם כל הפרמטרים מה-sidebar
    new_customers_plan, customers_df_annual, validation_df, tons_per_customer, pen_rate_df = calculate_plan(
        is_m, is_l, is_g, market_gr, pen_y1, tt_m, tt_l, tt_g, 
        annual_rev_targets, f_m, f_l, f_g, ip_kg, pdr
    )
    
    # --- הצגת התוצאות באזור המרכזי ---
    st.header("Recommended Action Plan")
    st.markdown("#### Table 1: Recommended New Customers to Acquire per Quarter")
    st.dataframe(new_customers_plan.T.style.format("{:,.2f}"))

    st.header("Projected Outcomes")
    st.markdown("#### Table 2: Cumulative Number of Customers (Year-End)")
    st.dataframe(customers_df_annual.T.style.format("{:,d}"))

    st.markdown("#### Table 3: Target vs. Actual Revenue")
    st.dataframe(validation_df.style.format({'Target Revenue': "${:,.0f}", 'Actual Revenue': "${:,.0f}", 'Difference': "${:,.0f}", 'Difference (%)': "{:,.2f}%"}))
    
    st.header("Chart: Target vs. Actual Annual Revenue ($)")
    plot_df = validation_df[['Target Revenue', 'Actual Revenue']].melt(ignore_index=False, var_name='Type', value_name='Revenue').reset_index()
    fig, ax = plt.subplots(figsize=(12, 6)); 
    sns.barplot(data=plot_df, x='index', y='Revenue', hue='Type', ax=ax, palette=['lightgray', 'skyblue'])
    ax.set_title('Target vs. Actual Annual Revenue', fontsize=16, weight='bold'); 
    ax.set_xlabel('Year'); ax.set_ylabel('Revenue ($)')
    ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    for p in ax.patches:
        height = p.get_height()
        ax.annotate(f'${height:,.0f}',(p.get_x() + p.get_width() / 2., height), ha='center', va='center', xytext=(0, 9), textcoords='offset points', fontsize=9)
    st.pyplot(fig)
    
    with st.expander("View Underlying Assumptions"):
        st.markdown("#### Table 4: Annual Tons per Single Customer (Target-Driven)")
        st.dataframe(tons_per_customer.T.style.format("{:,.2f}"))
        st.markdown("#### Table 5: Generated Penetration Rates to Meet Target (%)")
        st.dataframe((pen_rate_df.T*100).style.format("{:,.1f}%"))
else:
    st.info("Set your parameters in the sidebar and click 'Run Analysis' to see the results.")

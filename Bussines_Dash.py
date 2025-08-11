# app.py

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.interpolate import PchipInterpolator

# --- הגדרת העיצוב לדף ולגרפים ---
st.set_page_config(layout="wide", page_title="Multi-Product Business Plan Dashboard")
sns.set_theme(style="whitegrid")

# --- פונקציית החישוב המרכזית ---
def calculate_plan(is_m, is_l, is_g, market_gr, pen_y1, tt_m, tt_l, tt_g, 
                   annual_rev_targets, f_m, f_l, f_g, ip_kg, pdr):
    
    START_YEAR = 2025
    NUM_YEARS = 6
    years = np.array([START_YEAR + i for i in range(NUM_YEARS)])
    quarters_index = pd.date_range(start=f'{START_YEAR}-01-01', periods=NUM_YEARS*4, freq='QE')
    customer_types = ['Medium', 'Large', 'Global']

    # ... (כל לוגיקת החישוב מועתקת לכאן ללא שינוי)
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
    if total_focus == 0: return {"error": "Total Sales Focus must be greater than 0."}
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
        
    customers_df_quarterly_final = cumulative_customers.round().astype(int)
    revenue_per_customer_type_q = tons_per_cust_q.mul(price_per_ton_q, axis=0)
    actual_revenue_q = (revenue_per_customer_type_q * customers_df_quarterly_final).sum(axis=1)
    
    # --- התיקון המרכזי ---
    # ודא שגם ההכנסה בפועל וגם ההכנסה המתוכננת משתמשות באינדקס מספרי של שנים
    annual_revenue_series = actual_revenue_q.resample('YE').sum()
    annual_revenue_series.index = years

    annual_revenue_targets_series = pd.Series(annual_rev_targets, index=years)
    
    return {
        "new_customers_plan": new_customers_plan,
        "cumulative_customers": customers_df_quarterly_final,
        "annual_revenue": annual_revenue_series,
        "annual_revenue_targets": annual_revenue_targets_series,
        "tons_per_customer": tons_per_customer,
        "pen_rate_df": pen_rate_df,
        "error": None
    }

# --- פונקציה למתכנן הלידים ---
def create_lead_plan(new_customers_plan, success_rates, time_aheads):
    lead_plan = pd.DataFrame(0.0, index=new_customers_plan.index, columns=new_customers_plan.columns)
    for q_date, row in new_customers_plan.iterrows():
        for c_type in new_customers_plan.columns:
            new_cust_count = row[c_type]
            if new_cust_count > 0:
                success_rate = success_rates[c_type] / 100
                time_ahead = time_aheads[c_type]
                
                leads_to_contact = new_cust_count / success_rate if success_rate > 0 else 0
                contact_date = q_date - pd.DateOffset(months=time_ahead)
                
                contact_quarter_start = contact_date.to_period('Q').start_time
                matching_quarters = lead_plan.index[lead_plan.index.to_period('Q') == contact_quarter_start.to_period('Q')]
                if not matching_quarters.empty:
                    lead_plan.loc[matching_quarters[0], c_type] += leads_to_contact

    return lead_plan.round(2)

# --- הגדרת כותרת ראשית ---
st.title("📊 Multi-Product Business Plan Dashboard")

# --- הגדרת קלט למוצרים ---
products = ["Product 1", "Product 2"]
product_inputs = {}

with st.sidebar:
    # ... (כל הגדרות הסיידבר נשארו זהות לחלוטין)
    st.title("Business Plan Controls")
    with st.expander("5. Lead Generation Parameters (Global)"):
        lead_params = { 'success_rates': {}, 'time_aheads': {} }
        for c_type in ['Medium', 'Large', 'Global']:
            lead_params['success_rates'][c_type] = st.slider(f'Success Rate (%) - {c_type}', 0, 100, 50, key=f'sr_{c_type}')
            lead_params['time_aheads'][c_type] = st.slider(f'Time Ahead (Months) - {c_type}', 0, 24, 8, key=f'ta_{c_type}')
    for product in products:
        st.header(product)
        product_inputs[product] = {}
        with st.expander(f"1. Initial Customer Value", expanded=False):
            product_inputs[product]['is_m'] = st.number_input('Initial Tons/Customer - Medium:', 0.0, value=1.5, step=0.1, key=f'is_m_{product}')
            product_inputs[product]['is_l'] = st.number_input('Initial Tons/Customer - Large:', 0.0, value=10.0, step=1.0, key=f'is_l_{product}')
            product_inputs[product]['is_g'] = st.number_input('Initial Tons/Customer - Global:', 0.0, value=40.0, step=2.0, key=f'is_g_{product}')
        with st.expander(f"2. Customer Value Growth", expanded=False):
            product_inputs[product]['market_gr'] = st.slider('Annual Market Growth Rate (%):', 0.0, 20.0, 6.4, 0.1, key=f'mgr_{product}')
            product_inputs[product]['pen_y1'] = st.slider('Penetration Rate Year 1 (%):', 1.0, 20.0, 7.5, 0.1, key=f'pen_y1_{product}')
            st.markdown("---")
            product_inputs[product]['tt_m'] = st.number_input('Target Tons/Cust Year 5 - Medium:', 0.0, value=89.0, key=f'tt_m_{product}')
            product_inputs[product]['tt_l'] = st.number_input('Target Tons/Cust Year 5 - Large:', 0.0, value=223.0, key=f'tt_l_{product}')
            product_inputs[product]['tt_g'] = st.number_input('Target Tons/Cust Year 5 - Global:', 0.0, value=536.0, key=f'tt_g_{product}')
        with st.expander(f"3. Revenue Targets & Sales Strategy", expanded=False):
            st.markdown("**Target Annual Revenue ($)**")
            default_revenues = [400000, 1200000, 2500000, 4000000, 6000000, 8000000]
            rev_targets = []
            for i in range(6):
                year_num = i + 1
                rev_slider_val = st.slider(f'Year {year_num}:', 0, 60_000_000, default_revenues[i], 50000, format="$%d", key=f'rev_y{year_num}_{product}')
                rev_targets.append(rev_slider_val)
            product_inputs[product]['annual_rev_targets'] = rev_targets
            st.markdown("---")
            st.markdown("**Sales Focus (%)**")
            product_inputs[product]['f_m'] = st.slider('Medium:', 0, 100, 60, 5, key=f'f_m_{product}')
            product_inputs[product]['f_l'] = st.slider('Large:', 0, 100, 30, 5, key=f'f_l_{product}')
            product_inputs[product]['f_g'] = st.slider('Global:', 0, 100, 10, 5, key=f'f_g_{product}')
        with st.expander(f"4. Pricing Assumptions", expanded=False):
            product_inputs[product]['ip_kg'] = st.number_input('Initial Price per Kg ($):', 0.0, value=15.0, step=0.5, key=f'ip_kg_{product}')
            product_inputs[product]['pdr'] = st.slider('Quarterly Price Decay (%):', 0.0, 15.0, 2.5, 0.1, key=f'pdr_{product}')
    run_button = st.sidebar.button("Run Full Analysis", use_container_width=True)

# --- הרצה וסיכום ---
if run_button:
    # ... (כל קוד ההרצה והצגת התוצאות נשאר זהה לחלוטין)
    results = {}
    has_error = False
    for product in products:
        res = calculate_plan(**product_inputs[product])
        if res["error"]:
            st.error(f"Error for {product}: {res['error']}")
            has_error = True
            break
        results[product] = res
    if not has_error:
        tab1, tab2, tab_summary = st.tabs(["Product 1", "Product 2", "Overall Summary"])
        for product in products:
            tab = tab1 if product == "Product 1" else tab2
            with tab:
                st.header(f"Results for {product}")
                lead_plan = create_lead_plan(results[product]["new_customers_plan"], **lead_params)
                st.subheader("Lead Generation")
                st.markdown("#### Table 0: Recommended Lead Contact Plan")
                st.dataframe(lead_plan.T.style.format("{:,.2f}"))
                st.subheader("Action Plan & Outcomes")
                new_customers_plan = results[product]["new_customers_plan"]
                customers_df_annual = results[product]["cumulative_customers"].resample('YE').last()
                # שימוש באינדקס המספרי הנכון
                customers_df_annual.index = results[product]["annual_revenue_targets"].index
                validation_df = pd.DataFrame({'Target Revenue': results[product]['annual_revenue_targets'],'Actual Revenue': results[product]['annual_revenue']})
                validation_df['Difference'] = validation_df['Actual Revenue'] - validation_df['Target Revenue']
                validation_df['Difference (%)'] = validation_df['Difference'] / validation_df['Target Revenue'].replace(0, np.nan) * 100
                st.markdown("#### Table 1: Recommended New Customers to Acquire per Quarter")
                st.dataframe(new_customers_plan.round(2).T.style.format("{:,.2f}"))
                st.markdown("#### Table 2: Cumulative Number of Customers (Year-End)")
                st.dataframe(customers_df_annual.T.style.format("{:,d}"))
                st.markdown("#### Table 3: Target vs. Actual Revenue")
                st.dataframe(validation_df.style.format({'Target Revenue': "${:,.0f}", 'Actual Revenue': "${:,.0f}", 'Difference': "${:,.0f}", 'Difference (%)': "{:,.2f}%"}))
                st.markdown("#### Chart: Target vs. Actual Annual Revenue ($)")
                plot_df = validation_df[['Target Revenue', 'Actual Revenue']].melt(ignore_index=False, var_name='Type', value_name='Revenue').reset_index()
                fig, ax = plt.subplots(figsize=(12, 6))
                sns.barplot(data=plot_df, x='index', y='Revenue', hue='Type', ax=ax, palette=['lightgray', 'skyblue'])
                ax.set_title(f'Target vs. Actual Revenue - {product}', fontsize=16)
                st.pyplot(fig)
        with tab_summary:
            st.header("Overall Summary (All Products)")
            summary_revenue_list = [results[p]['annual_revenue'] for p in products]
            summary_revenue = pd.concat(summary_revenue_list, axis=1).sum(axis=1)
            summary_customers_list = [results[p]['cumulative_customers'].resample('YE').last() for p in products]
            # Ensure all customer DFs have the same integer index before summing
            for i, df in enumerate(summary_customers_list):
                df.index = summary_revenue.index
            summary_customers = pd.concat(summary_customers_list, axis=1).sum(axis=1)
            st.markdown("#### Summary: Total Revenue per Year")
            st.dataframe(summary_revenue.to_frame(name="Total Revenue").style.format("${:,.0f}"))
            st.markdown("#### Summary: Total Cumulative Customers per Year")
            st.dataframe(summary_customers.to_frame(name="Total Customers").T.style.format("{:,d}"))
            st.markdown("#### Chart: Total Revenue Breakdown by Product")
            all_revenues = {p: results[p]['annual_revenue'] for p in products}
            summary_plot_df = pd.DataFrame(all_revenues)
            fig_sum, ax_sum = plt.subplots(figsize=(12, 6))
            summary_plot_df.plot(kind='bar', stacked=True, ax=ax_sum, colormap='viridis')
            ax_sum.set_title('Total Revenue by Product (Stacked)', fontsize=16)
            ax_sum.set_ylabel('Revenue ($)')
            ax_sum.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
            ax_sum.set_xticklabels(summary_plot_df.index.to_series().astype(str), rotation=45)
            st.pyplot(fig_sum)
else:
    st.info("Set your parameters in the sidebar and click 'Run Full Analysis' to see the results.")

# app.py

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.interpolate import PchipInterpolator
import io

# --- Page Config & Chart Styling ---
st.set_page_config(layout="wide", page_title="Advanced Business Plan Dashboard")
sns.set_theme(style="darkgrid", font_scale=1.1, palette="viridis")


# --- Session State Initialization ---
if 'products' not in st.session_state:
    st.session_state.products = ["Product A", "Product B"]
if 'results' not in st.session_state:
    st.session_state.results = {}

# --- Helper Functions ---
@st.cache_data
def to_excel(results_dict):
    """Creates an Excel file from the results dictionary."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Loop ONLY over products
        for product_name, data in results_dict.items():
            if product_name == 'summary':
                continue

            df_acquired_cust_T = data['acquired_customers_plan'].T
            df_lead_plan_T = data['lead_plan'].T
            df_cum_cust_q_T = data["cumulative_customers"].T
            df_validation = data['validation_df']
            
            for df in [df_acquired_cust_T, df_lead_plan_T, df_cum_cust_q_T]:
                df.columns = [f"{c.year}-Q{c.quarter}" for c in df.columns]

            df_acquired_cust_T.to_excel(writer, sheet_name=product_name, startrow=2, index=True)
            writer.sheets[product_name].cell(row=1, column=1, value="Acquired New Customers per Quarter")
            
            df_lead_plan_T.to_excel(writer, sheet_name=product_name, startrow=df_acquired_cust_T.shape[0] + 6, index=True)
            writer.sheets[product_name].cell(row=df_acquired_cust_T.shape[0] + 5, column=1, value="Recommended Lead Contact Plan")
            
            df_cum_cust_q_T.to_excel(writer, sheet_name=product_name, startrow=df_acquired_cust_T.shape[0] + df_lead_plan_T.shape[0] + 10, index=True)
            writer.sheets[product_name].cell(row=df_acquired_cust_T.shape[0] + df_lead_plan_T.shape[0] + 9, column=1, value="Cumulative Customers (Quarterly)")

            df_validation.to_excel(writer, sheet_name=product_name, startrow=df_acquired_cust_T.shape[0] + df_lead_plan_T.shape[0] + df_cum_cust_q_T.shape[0] + 14, index=True)
            writer.sheets[product_name].cell(row=df_acquired_cust_T.shape[0] + df_lead_plan_T.shape[0] + df_cum_cust_q_T.shape[0] + 13, column=1, value="Target vs. Actual Revenue")

        if "summary" in results_dict:
            summary_data = results_dict["summary"]
            summary_revenue_df = summary_data["summary_revenue"]
            summary_customers_df = summary_data["summary_customers_raw"] # Use raw data
            
            summary_revenue_df.to_excel(writer, sheet_name="Overall Summary", startrow=2, index=True)
            writer.sheets["Overall Summary"].cell(row=1, column=1, value="Total Revenue per Year")
            
            summary_customers_df_T = summary_customers_df.to_frame("Total Customers").T
            summary_customers_df_T.columns = [f"{c.year}-Q{c.quarter}" for c in summary_customers_df_T.columns]
            summary_customers_df_T.to_excel(writer, sheet_name="Overall Summary", startrow=10, index=True)
            writer.sheets["Overall Summary"].cell(row=9, column=1, value="Total Cumulative Customers (Quarterly)")

    return output.getvalue()

def calculate_plan(is_m, is_l, is_g, market_gr, pen_y1, tt_m, tt_l, tt_g, 
                   annual_rev_targets, f_m, f_l, f_g, ip_kg, pdr, price_floor):
    """Main calculation engine for a single product."""
    START_YEAR = 2025
    NUM_YEARS = 6
    years = np.array([START_YEAR + i for i in range(NUM_YEARS)])
    quarters_index = pd.date_range(start=f'{START_YEAR}-01-01', periods=NUM_YEARS*4, freq='QE')
    customer_types = ['Medium', 'Large', 'Global']
    
    tons_per_customer = pd.DataFrame(index=years, columns=customer_types, dtype=float)
    tons_per_customer.loc[START_YEAR] = [is_m, is_l, is_g]
    initial_tons = {'Medium': is_m, 'Large': is_l, 'Global': is_g}
    target_tons = {'Medium': tt_m, 'Large': tt_l, 'Global': tt_g}
    pen_rate_df = pd.DataFrame(index=range(1, NUM_YEARS + 1), columns=customer_types)
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
            
    prices = []
    current_price = ip_kg
    decay_rate = pdr / 100.0
    for _ in range(len(quarters_index)):
        prices.append(current_price)
        next_price = current_price * (1 - decay_rate)
        current_price = max(next_price, price_floor)
        
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
    customers_df_quarterly_final = cumulative_customers
    revenue_per_customer_type_q = tons_per_cust_q.mul(price_per_ton_q, axis=0)
    actual_revenue_q = (revenue_per_customer_type_q * cumulative_customers.round().astype(int)).sum(axis=1)
    
    annual_revenue_series = actual_revenue_q.resample('YE').sum()
    annual_revenue_series.index = years
    annual_revenue_targets_series = pd.Series(annual_rev_targets, index=years)
    
    return {
        "cumulative_customers": customers_df_quarterly_final,
        "annual_revenue": annual_revenue_series,
        "annual_revenue_targets": annual_revenue_targets_series,
        "error": None
    }

def create_lead_plan(acquired_customers_plan, success_rates, time_aheads_in_quarters):
    """Calculates leads based on a plan of acquired (integer) customers."""
    quarters_index = acquired_customers_plan.index
    lead_plan = pd.DataFrame(0, index=quarters_index, columns=acquired_customers_plan.columns)
    
    for q_date, row in acquired_customers_plan.iterrows():
        for c_type in acquired_customers_plan.columns:
            new_cust_count = row[c_type]
            if new_cust_count > 0:
                success_rate = success_rates[c_type] / 100
                time_ahead_q = time_aheads_in_quarters[c_type]
                leads_to_contact = np.ceil(new_cust_count / success_rate if success_rate > 0 else 0)
                
                contact_date = q_date - pd.DateOffset(months=time_ahead_q * 3)
                
                try:
                    target_quarter = pd.Timestamp(contact_date).to_period('Q').to_timestamp(how='end', freq='Q')
                    if target_quarter in lead_plan.index:
                        lead_plan.loc[target_quarter, c_type] += leads_to_contact
                except:
                    pass
    return lead_plan.astype(int)

# --- Main App UI ---
st.title("🚀 Dynamic Multi-Product Business Plan Dashboard")

with st.sidebar:
    st.title("Business Plan Controls")
    with st.expander("Manage Products"):
        for i, product_name in enumerate(st.session_state.products):
            st.session_state.products[i] = st.text_input(f"Product {i+1} Name", value=product_name, key=f"pname_{i}")
        new_product_name = st.text_input("New Product Name", key="new_product_name_input")
        if st.button("Add Product") and new_product_name:
            if new_product_name not in st.session_state.products:
                st.session_state.products.append(new_product_name)
                st.rerun()
            else:
                st.warning("Product name already exists.")

    with st.expander("Lead Generation Parameters (Global)"):
        lead_params = { 'success_rates': {}, 'time_aheads_in_quarters': {} }
        customer_types_for_leads = ['Medium', 'Large', 'Global']
        lead_params['success_rates']['Medium'] = st.slider(f'Success Rate (%) - Medium', 0, 100, 50, key=f'sr_Medium')
        lead_params['time_aheads_in_quarters']['Medium'] = st.slider(f'Time Ahead (Quarters) - Medium', 1, 8, 3, key=f'ta_Medium')
        lead_params['success_rates']['Large'] = st.slider(f'Success Rate (%) - Large', 0, 100, 40, key=f'sr_Large')
        lead_params['time_aheads_in_quarters']['Large'] = st.slider(f'Time Ahead (Quarters) - Large', 1, 8, 4, key=f'ta_Large')
        lead_params['success_rates']['Global'] = st.slider(f'Success Rate (%) - Global', 0, 100, 30, key=f'sr_Global')
        lead_params['time_aheads_in_quarters']['Global'] = st.slider(f'Time Ahead (Quarters) - Global', 1, 12, 6, key=f'ta_Global')
    
    product_inputs = {}
    for product in st.session_state.products:
        st.header(product)
        product_inputs[product] = {}
        with st.expander(f"1. Initial Customer Value", expanded=False):
            product_inputs[product]['is_m'] = st.number_input('Initial Tons/Customer - Medium:', 0.0, value=1.5, step=0.1, key=f'is_m_{product}')
            product_inputs[product]['is_l'] = st.number_input('Initial Tons/Customer - Large:', 0.0, value=10.0, step=1.0, key=f'is_l_{product}')
            product_inputs[product]['is_g'] = st.number_input('Initial Tons/Customer - Global:', 0.0, value=40.0, step=2.0, key=f'is_g_{product}')
        with st.expander(f"2. Customer Value Growth", expanded=False):
            product_inputs[product]['market_gr'] = st.slider('Annual Market Growth Rate (%):', 0.0, 20.0, 6.4, 0.1, key=f'mgr_{product}')
            product_inputs[product]['pen_y1'] = st.slider('Penetration Rate Year 1 (%):', 1.0, 20.0, 7.5, 0.1, key=f'pen_y1_{product}')
            product_inputs[product]['tt_m'] = st.number_input('Target Tons/Cust Year 5 - Medium:', 0.0, value=89.0, key=f'tt_m_{product}')
            product_inputs[product]['tt_l'] = st.number_input('Target Tons/Cust Year 5 - Large:', 0.0, value=223.0, key=f'tt_l_{product}')
            product_inputs[product]['tt_g'] = st.number_input('Target Tons/Cust Year 5 - Global:', 0.0, value=536.0, key=f'tt_g_{product}')
        with st.expander(f"3. Revenue Targets & Sales Strategy", expanded=False):
            st.markdown("**Target Annual Revenue ($)**")
            default_revenues = [300000, 2700000, 5500000, 12000000, 32000000, 40000000]
            rev_targets = []
            for i in range(6):
                year_num = i + 1
                rev_slider_val = st.slider(f'Year {year_num}:', 0, 50_000_000, default_revenues[i], 100000, format="$%d", key=f'rev_y{year_num}_{product}')
                rev_targets.append(rev_slider_val)
            product_inputs[product]['annual_rev_targets'] = rev_targets
            st.markdown("---")
            st.markdown("**Sales Focus (%)**")
            product_inputs[product]['f_m'] = st.slider('Medium:', 0, 100, 50, 5, key=f'f_m_{product}')
            product_inputs[product]['f_l'] = st.slider('Large:', 0, 100, 30, 5, key=f'f_l_{product}')
            product_inputs[product]['f_g'] = st.slider('Global:', 0, 100, 20, 5, key=f'f_g_{product}')
        with st.expander(f"4. Pricing Assumptions", expanded=False):
            product_inputs[product]['ip_kg'] = st.number_input('Initial Price per Kg ($):', 0.0, value=18.0, step=0.5, key=f'ip_kg_{product}')
            product_inputs[product]['pdr'] = st.slider('Quarterly Price Decay (%):', 0.0, 10.0, 3.65, 0.05, key=f'pdr_{product}')
            product_inputs[product]['price_floor'] = st.number_input('Minimum Price ($):', 0.0, value=14.0, step=0.5, key=f'price_floor_{product}')
    
    run_button = st.sidebar.button("Run Full Analysis", use_container_width=True)

# --- App Logic and Display ---
if run_button:
    results_data = {}
    for product in st.session_state.products:
        res = calculate_plan(**product_inputs[product])
        if res.get("error"):
            st.error(f"Error for {product}: {res['error']}"); st.stop()
        
        final_cumulative = res["cumulative_customers"].round().astype(int)
        acquired_customers = final_cumulative.diff(axis=0).fillna(final_cumulative.iloc[0]).clip(lower=0).astype(int)
        
        res['acquired_customers_plan'] = acquired_customers
        res['cumulative_customers'] = final_cumulative
        res['lead_plan'] = create_lead_plan(acquired_customers, **lead_params)
        results_data[product] = res
    st.session_state.results = results_data

if st.session_state.results:
    results = st.session_state.results
    tabs = st.tabs([*st.session_state.products, "Overall Summary"])
    
    for i, product_name in enumerate(st.session_state.products):
        with tabs[i]:
            st.header(f"Results for {product_name}")
            
            lead_plan_display = results[product_name]["lead_plan"].T
            lead_plan_display.columns = [f"{c.year}-Q{c.quarter}" for c in lead_plan_display.columns]

            acquired_customers_display = results[product_name]["acquired_customers_plan"].T
            acquired_customers_display.columns = [f"{c.year}-Q{c.quarter}" for c in acquired_customers_display.columns]
            
            cum_cust_display = results[product_name]["cumulative_customers"].T
            cum_cust_display.columns = [f"{c.year}-Q{c.quarter}" for c in cum_cust_display.columns]

            validation_df = pd.DataFrame({
                'Target Revenue': results[product_name]['annual_revenue_targets'],
                'Actual Revenue': results[product_name]['annual_revenue']
            })
            validation_df.index.name = "Year"
            results[product_name]['validation_df'] = validation_df
            
            st.subheader("Lead Generation")
            st.markdown("#### Table 0: Recommended Lead Contact Plan")
            st.dataframe(lead_plan_display.style.format("{:d}"))

            st.subheader("Action Plan & Outcomes")
            st.markdown("#### Table 1: Acquired New Customers per Quarter")
            st.dataframe(acquired_customers_display.style.format("{:d}"))

            st.markdown("#### Table 2: Cumulative Number of Customers (Quarterly)")
            st.dataframe(cum_cust_display.style.format("{:,d}"))

            st.markdown("#### Table 3: Target vs. Actual Revenue")
            st.dataframe(validation_df.style.format({'Target Revenue': "${:,.0f}", 'Actual Revenue': "${:,.0f}"}))
            
            st.markdown("#### Chart: Target vs. Actual Annual Revenue ($)")
            plot_df = validation_df.reset_index()
            plot_df_melted = plot_df.melt(id_vars='Year', var_name='Type', value_name='Revenue')
            
            fig, ax = plt.subplots(figsize=(14, 7))
            barplot = sns.barplot(data=plot_df_melted, x='Year', y='Revenue', hue='Type', ax=ax, palette="mako")
            
            ax.set_title(f'Target vs. Actual Revenue - {product_name}', fontsize=18, weight='bold')
            ax.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x/1_000_000:.1f}M"))
            ax.set_xlabel("Year", fontsize=12)
            ax.set_ylabel("Revenue", fontsize=12)

            for container in barplot.containers:
                ax.bar_label(container, fmt='${:,.0f}', padding=5, fontsize=9, rotation=90)
            st.pyplot(fig)

    with tabs[-1]:
        st.header("Overall Summary (All Products)")
        
        summary_revenue_list = [results[p]['annual_revenue'] for p in st.session_state.products]
        summary_revenue_df = pd.concat(summary_revenue_list, axis=1).sum(axis=1).to_frame(name="Total Revenue")
        
        summary_customers_list = [results[p]['cumulative_customers'] for p in st.session_state.products]
        summary_customers_total_q_raw = pd.concat(summary_customers_list, axis=1).sum(axis=1)
        summary_customers_total_q = summary_customers_total_q_raw.round().astype(int)
        
        st.markdown("#### Summary: Total Revenue per Year")
        st.dataframe(summary_revenue_df.style.format("${:,.0f}"))

        summary_customers_display = summary_customers_total_q.to_frame(name="Total Customers").T
        summary_customers_display.columns = [f"{c.year}-Q{c.quarter}" for c in summary_customers_display.columns]
        st.markdown("#### Summary: Total Cumulative Customers (Quarterly)")
        st.dataframe(summary_customers_display.style.format("{:,d}"))

        st.markdown("#### Chart: Total Revenue Breakdown by Product")
        all_revenues = {p: results[p]['annual_revenue'] for p in st.session_state.products}
        summary_plot_df = pd.DataFrame(all_revenues)
        summary_plot_df_melted = summary_plot_df.reset_index().rename(columns={'index': 'Year'}).melt(id_vars='Year', var_name='Product', value_name='Revenue')
        
        fig_sum, ax_sum = plt.subplots(figsize=(15, 8))
        
        summary_barplot = sns.barplot(data=summary_plot_df_melted, x='Year', y='Revenue', hue='Product', ax=ax_sum, palette="rocket_r")

        for container in ax_sum.containers:
            ax_sum.bar_label(
                container,
                fmt='$ {:,.0f}',
                rotation=90,
                padding=8,
                fontsize=10,
                color='white',
                fontweight='bold'
            )

        ax_sum.set_title('Total Revenue Breakdown by Product', fontsize=18, weight='bold')
        ax_sum.set_ylabel('Revenue ($)', fontsize=12)
        ax_sum.set_xlabel('Year', fontsize=12)
        ax_sum.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x/1_000_000:.0f}M"))
        ax_sum.tick_params(axis='x', rotation=0)
        st.pyplot(fig_sum)
    
    excel_results_to_pass = {}
    for prod_name, res_data in results.items():
        excel_results_to_pass[prod_name] = res_data.copy()
    
    summary_for_excel = {
        "summary_revenue": summary_revenue_df,
        "summary_customers_raw": summary_customers_total_q_raw
    }
    
    excel_data = to_excel({**excel_results_to_pass, "summary": summary_for_excel})
    st.download_button(label="📥 Download Full Report to Excel", data=excel_data, file_name="Business_Plan_Full_Report.xlsx")

if not run_button and not st.session_state.results:
    st.info("Set your parameters in the sidebar and click 'Run Full Analysis' to see the results.")

# Create and make request for transactions
import requests
import yaml
import pandas as pd
from io import StringIO
from datetime import date, timedelta
import numpy as np
import os
from pandas.io.formats.style import Styler

style_template = [
            # Table
            {'selector': 'table',
             'props': [('border-collapse', 'collapse'), ('width', '100%')]},

            # Headers
            {'selector': 'th',
             'props': [('border', '1px solid #999'),
                       ('padding', '6px'),
                       ('background-color', '#f5f5f5')]},

            # Cells
            {'selector': 'td',
             'props': [('border', '1px solid #999'),
                       ('padding', '6px')]},

        ]


def get_config(path_2_filename = "",filename = "config.yaml"):
    #importing config file
    with open(path_2_filename + filename, 'r') as f:
        config = yaml.safe_load(f)
    return config

def get_YNAB_transactions(YNAB_API_token,budget_id):
    # Call YNAB APIs for transactions, given a buget ID and token
    url = f"https://api.ynab.com/v1/budgets/{budget_id}/transactions"
    r = requests.get(url, headers={"Authorization":"Bearer "+ YNAB_API_token}).json()
    return r

def get_YNAB_categories(YNAB_API_token,budget_id):
     # Get parent categeory names & get group_ids of shared groups
    url = f"https://api.ynab.com/v1/budgets/{budget_id}/categories"
    r = requests.get(url, headers={"Authorization":"Bearer "+ YNAB_API_token}).json()["data"]["category_groups"]
    return r

def make_category_is_shared_mapping(shared_groups,r_categories):
     # make a dictionary to map if each category is a shared expense or not
    category_dict = {}
    for r_category in r_categories:
        if r_category['name'] in shared_groups:
            shared = True
        else:
            shared = False
        for n in range(len(r_category['categories'])):
            category_dict[r_category['categories'][n]["id"]] = shared
    return category_dict

def get_date_range(period=None,start_date=None,end_date=None):
    
    if (start_date is not None) & (end_date is not None):
        return np.datetime64(start_date), np.datetime64(end_date)
    
    elif period == "last_month":
        d = date.today()
        start_date = (d - timedelta(days=d.day)).replace(day=1)
        next_month = start_date.replace(day=28) + timedelta(days=4)
        end_date = next_month - timedelta(days=next_month.day)
        return np.datetime64(start_date), np.datetime64(end_date)

    elif period == "last_week":
        # Get the current date and assign it to the variable 'today'
        today = date.today() - timedelta(days=1) # take from yesterday, to ensure all of Sunday has passed

        # Calculate the offset needed to go back to the most recent Sunday
        offset = (today.weekday() - 6) % 7

        # Calculate the date of the most recent Sunday by subtracting the offset from the current date
        last_sunday = today - timedelta(days=offset)

        # Print the date of the most recent Sunday
        start_date = last_sunday - timedelta(days=6)
        end_date = last_sunday
        
        return np.datetime64(start_date), np.datetime64(end_date)
    
    else:
        exit("Improperly assigned start_date, end_date or period. See config.YAML")

def get_account_holder(df,account_holders):
    df['account_holder'] = df['account_name'].case_when(caselist=[(df['account_name'].str.contains(account_holders[0]), account_holders[0]),  # condition, replacement 
                                                                  (df['account_name'].str.contains(account_holders[1]), account_holders[1])])
    return df

def explode_subtransactions(df):
    # Explode out subtransactions
    df['subtransactions'] = df['subtransactions'].apply(lambda y: np.nan if len(y)==0 else y)
    sub_transactions = df[['date','account_name','approved','import_payee_name','subtransactions']][df['subtransactions'].notnull()]

    sub_transactions_list = []
    for index, row in sub_transactions.iterrows():
        my_date = row['date']
        my_account = row['account_name']
        my_approved = row['approved']
        my_import_payee_name = row['import_payee_name']
        for item in row['subtransactions']:
            df_sub = pd.DataFrame(item, index=[index])
            df_sub['date'] = my_date
            df_sub['account_name'] = my_account
            df_sub['approved'] = my_approved
            df_sub['import_payee_name'] = my_import_payee_name
            sub_transactions_list.append(df_sub)
    
    sub_transactions_df = pd.concat(sub_transactions_list, ignore_index=True)

    # Drop parent split transactions
    df = df[df['subtransactions'].isnull()]
    # Add back in split transactions
    df = pd.concat([df, sub_transactions_df], ignore_index=True)
    return df

def clean_transactions_response(r_transactions,category_dict,categories_to_ignore,account_holders,shared_accounts,period=None,start_date=None,end_date=None):
    
    start_date, end_date = get_date_range(period,start_date,end_date)
    # Import into pandas
    df = pd.DataFrame(r_transactions["data"]["transactions"])

    # Drop uncleared transactions
    df = df[df['cleared'] != "uncleared"]
    
    df= explode_subtransactions(df)

    # Drop non shared accounts
    df['a'] = df['category_id'].map(category_dict)
    df = df[~df['account_name'].isin(shared_accounts)]

    # Drop non shared transactions
    df['is_shared'] = df['category_id'].map(category_dict)
    df = df[df['is_shared']!=False]
    
    # Drop ignored categories
    df = df[~df['category_name'].isin(categories_to_ignore)]

    # more cleaning
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"] / 1000
    df = df[df['date'].between(start_date, end_date)]

    df = get_account_holder(df,account_holders)

    return df.sort_values(by=['account_name','date'],ascending=True)

def mom_arrow(val):
    if pd.isna(val):
        return ''
    if val > 0:
        return f'▲ {val:.0f}%'
    if val < 0:
        return f'▼ {abs(val):.0f}%'
    return '0.0%'

def create_summary_report(r_transactions,start_date=None):
    # Create summary report and store in HTML string
    curr_month = pd.to_datetime(start_date).to_period('M')
    df = pd.DataFrame(r_transactions["data"]["transactions"])
    df = explode_subtransactions(df)
    df = df[~df['category_name'].isin(['Uncategorized','Inflow: Ready to Assign'])]
    df['month'] = pd.to_datetime(df['date']).dt.to_period('M')
    df["amount"] = df["amount"] / 1000
    df_current = df[df['month'] == curr_month]
    df_prev = df[df['month'] == curr_month - 1]
    
    df_curr_month = df_current.groupby('category_name')['amount'].sum()
    df_prev_month = df_prev.groupby('category_name')['amount'].sum()
    df_three_month_avg = df[df['month'].isin([curr_month - 1, curr_month - 2, curr_month -3])].groupby('category_name')['amount'].sum() / 3

    report = df_curr_month.to_frame(name='Current Month')
    report = report.join(df_prev_month.to_frame(name='Previous Month'), how='outer')
    report = report.join(df_three_month_avg.to_frame(name='Prev Three Month Avg'), how='outer')
    report = report.fillna(0)
    report['% Change MoM'] = ((report['Current Month'] - report['Previous Month'])/ report['Previous Month'].replace(0, pd.NA)* 100).round(1)
    report['% Change 3 Month'] = ((report['Current Month'] - report['Prev Three Month Avg'])/ report['Prev Three Month Avg'].replace(0, pd.NA)* 100).round(1)
    
    report.sort_values(by='Current Month', ascending=True, inplace=True)

    report['MoM Change'] = report['% Change MoM'].apply(mom_arrow)
    report['Change From 3 month'] = report['% Change 3 Month'].apply(mom_arrow)


    for col in ['Current Month', 'Previous Month']:
        total = report[col].sum()
        report[f'{col} %'] = (
            report[col] / total * 100
            if total != 0 else 0
        )

    columns_order = [
        'Current Month', 'Previous Month', 'Prev Three Month Avg', 'MoM Change', 'Change From 3 month']

    styler = (
    report[columns_order].style
        .set_table_styles(style_template)
        .format({
            'Current Month': '${:,.2f}',
            'Previous Month': '${:,.2f}',
            'Prev Three Month Avg': '${:,.2f}',
        })
)

    report_html = "<h2>Expense Summary</h2>" + styler.to_html()
    return report_html



def create_report_html(df):
    # Create report and store in HTML string
    columns_to_include = ["account_name","date","import_payee_name","category_name","memo","amount"]
    
    report_html  = ''
    df_cat = df[(df['category_name']!="Uncategorized") & (df['approved']==True)]
    report_html += "<h2>Shared Summary</h2>"
    account_holders_sum = df_cat.groupby('account_holder')['amount'].sum()
    if len(account_holders_sum) == 2:
        owed_amount = abs(round((account_holders_sum.iloc[0] - account_holders_sum.iloc[1]) / 2,2))
        if account_holders_sum.iloc[0] < account_holders_sum.iloc[1]:
            report_html += f"{account_holders_sum.index[1]} owes {account_holders_sum.index[0]} ${owed_amount}"
        elif account_holders_sum.iloc[0] > account_holders_sum.iloc[1]:
            report_html += f"{account_holders_sum.index[0]} owes {account_holders_sum.index[1]} ${owed_amount}"
        else:
            report_html += "Settled already!"
    else:
        report_html += f"error: Not 2 account holders. Found {account_holders_sum.index}"

    report_html += pd.DataFrame(account_holders_sum).style.set_table_styles(style_template).format({
        'amount': '${:,.2f}',
    }).to_html() + "<br><br>"

    report_html += "<h2>Categorized, shared expenses:</h2>"
    report_html += df_cat[columns_to_include].sort_values(by='date').style.set_table_styles(style_template).format({
            'date': '{:%b %d}',
            'amount': '${:,.2f}',
        }).to_html(index=False) + "<br>"

    df_uncat = df[df['approved']!=True]
    if len(df_uncat) > 0:
        report_html += "<h2>Uncategorized expenses (not included above):</h2>"
        report_html += df_uncat[columns_to_include].to_html(index=False) + "<br>"

        report_html += "<h2>Uncategorized summary:</h2>"
        report_html += pd.DataFrame(df_uncat.groupby('account_name')['amount'].sum()).to_html()
    return report_html

def initialize_report():
    config = get_config()
    token = os.environ['ynab_api_token']
    budget_id = config['YNAB']['budget_id']
    shared_groups = config['YNAB']['shared_groups']
    shared_accounts = config['YNAB']['shared_accounts']
    account_holders = config['YNAB']['account_holders']
    categories_to_ignore = config['YNAB']['categories_to_ignore']
    
    try:
        start_date = config['job']['start_date']
    except:
        start_date = None
    try:
        end_date = config['job']['end_date']
    except:
        end_date = None
    try:
        period = config['job']['period']
    except:
        period = None


    # Categories
    r_categories = get_YNAB_categories(token,budget_id)
    category_dict = make_category_is_shared_mapping(shared_groups,r_categories)

    # Transactions
    r_transactions = get_YNAB_transactions(token,budget_id)

    # Clean response & convert to dataframe
    df = clean_transactions_response(r_transactions,category_dict,categories_to_ignore,account_holders,shared_accounts,period=period,start_date=start_date,end_date=end_date)

    html_str = ''
    if period is not None:
        start_date, end_date = get_date_range(period)
        html_str += create_summary_report(r_transactions,start_date=start_date)
    html_str += create_report_html(df)
    #create_summary_report(r_transactions,period=period,start_date="2025-09-01",end_date="2025-12-31")
    #html_str += create_summary_report(r_transactions,period=period,start_date="2025-09-01",end_date="2025-12-31")
    return html_str

if __name__ == '__main__':
    html_str = initialize_report()
    
    with open("ynab_report.html", "w") as file:
        file.write(html_str)

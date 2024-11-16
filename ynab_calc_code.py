# Create and make request for transactions
import requests
import yaml
import pandas as pd
from io import StringIO
from datetime import date, timedelta
import numpy as np
import os

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

def clean_transactions_response(r_transactions,category_dict,account_holders,period=None,start_date=None,end_date=None):
    
    start_date, end_date = get_date_range(period,start_date,end_date)
    # Import into pandas
    df = pd.DataFrame(r_transactions["data"]["transactions"])
    
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

    # Drop non shared transactions
    df['is_shared'] = df['category_id'].map(category_dict)
    df = df[df['is_shared']!=False]
    
    # more cleaning
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"] / 1000
    df = df[df['date'].between(start_date, end_date)]

    df = get_account_holder(df,account_holders)

    return df.sort_values(by=['date'],ascending=True)

def create_report_html(df):
    # Create report and store in HTML string
    columns_to_include = ["account_name","date","import_payee_name","category_name","memo","amount"]
    
    report_html  = ''
    df_cat = df[(df['category_name']!="Uncategorized") & (df['approved']==True)]
    report_html += "<h2>Shared Summary</h2>"
    account_holders_sum = df_cat.groupby('account_holder')['amount'].sum()
    if len(account_holders_sum) == 2:
        owed_amount = round((account_holders_sum.iloc[0] - account_holders_sum.iloc[1]) / 2,2)
        if account_holders_sum.iloc[0] < account_holders_sum.iloc[1]:
            report_html += f"{account_holders_sum.index[1]} owes {account_holders_sum.index[1]} ${owed_amount}"
        elif account_holders_sum.iloc[0] > account_holders_sum.iloc[1]:
            report_html += f"{account_holders_sum.index[0]} owes {account_holders_sum.index[1]} ${owed_amount}"
        else:
            report_html += "Settled already!"
    else:
        report_html += f"error: Not 2 account holders. Found {account_holders_sum.index}"

    report_html += pd.DataFrame(account_holders_sum).to_html() + "<br><br>"

    report_html += "<h2>Categorized, shared expenses:</h2>"
    report_html += df_cat[columns_to_include].to_html(index=False) + "<br>"

    report_html += "<h2>Uncategorized expenses (not included above):</h2>"
    df_uncat = df[(df['category_name']=="Uncategorized") | (df['approved']!=True)]
    report_html += df_uncat[columns_to_include].to_html(index=False) + "<br>"

    report_html += "<h2>Uncategorized summary:</h2>"
    report_html += pd.DataFrame(df_uncat.groupby('account_name')['amount'].sum()).to_html()
    return report_html

def initialize_report():
    config = get_config()
    token = os.environ['ynab_api_token']
    budget_id = config['YNAB']['budget_id']
    shared_groups = config['YNAB']['shared_groups']
    account_holders = config['YNAB']['account_holders']
    
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
    df = clean_transactions_response(r_transactions,category_dict,account_holders,period=period,start_date=start_date,end_date=end_date)

    html_str = create_report_html(df)
    
    return html_str

if __name__ == '__main__':
    html_str = initialize_report()
    
    with open("ynab_report.html", "w") as file:
        file.write(html_str)

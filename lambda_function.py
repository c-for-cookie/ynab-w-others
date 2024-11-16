import json
import boto3
import yaml
import ynab_calc_code as ycc

with open("config.yaml", 'r') as f:
        config = yaml.safe_load(f)

client = boto3.client('ses', region_name='us-east-2')


def lambda_handler(event, context):
    BODY_HTML = ycc.initialize_report()
    start_date, end_date = ycc.get_date_range(period=config['job']['period'],start_date=config['job']['start_date'],end_date=config['job']['end_date'])
    response = client.send_email(
    Destination={
        'ToAddresses': config['email']['recipients']
    },
    
    
    Message={
        'Body': {
            'Html': {
                    'Charset': 'UTF-8',
                    'Data': BODY_HTML,
                },
            'Text': {
                'Charset': 'UTF-8',
                'Data': 'yada yada yada stuff',
            }
        },
        'Subject': {
            'Charset': 'UTF-8',
            'Data': config['email']['subject'] + start_date.item().strftime('%A %m/%d/%Y') + " -> " + end_date.item().strftime('%A %m/%d/%Y'),
        },
    },
    Source=config['email']['sender']
    )
    
    print(response)
    
    return {
        'statusCode': 200,
        'body': json.dumps("Email Sent Successfully. MessageId is: " + response['MessageId'])
    }

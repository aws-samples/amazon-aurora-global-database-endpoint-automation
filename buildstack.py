import boto3
import sys
import time
import datetime
import argparse 
import re
import urllib3
from botocore.exceptions import ClientError
import os
import json


def buildstack(region):
# builds the stack
    try:
        
        client = boto3.client('cloudformation',region_name=region)

        create_stack_response = client.create_stack(
        StackName=stackname,
        TemplateBody=templateBody,
        NotificationARNs=[],
        Capabilities=[
            'CAPABILITY_NAMED_IAM',
        ],
        OnFailure='ROLLBACK'
        )

        stackuuid = create_stack_response['StackId']
        return stackuuid
    
    except ClientError as e:
        print("[ERROR]",e)
        raise
    except Exception as e:
        print("[ERROR]", e)

def checkstackstatus(region):
# checks stack building status    
    try:
        
        stack_building = True

        client = boto3.client('cloudformation',region_name=region)

        event_list = client.describe_stack_events(StackName=stackname).get("StackEvents")
        stack_event = event_list[0]

        if (stack_event.get('ResourceType') == 'AWS::CloudFormation::Stack' and stack_event.get('ResourceStatus') == 'CREATE_COMPLETE'):
            stack_building = False
            print("Stack construction completed for region...", region)
        elif (stack_event.get('ResourceType') == 'AWS::CloudFormation::Stack' and stack_event.get('ResourceStatus') == 'ROLLBACK_COMPLETE'):
            stack_building = False
            print("Stack construction failed for region...", region)
            sys.exit(1)
        else:
            print("Stack creation in progress for region...", region)

        return stack_building

    except ClientError as e:
        print("[ERROR]",e)
        raise
    except Exception as e:
        print("[ERROR]", e)

def checkstackname(region):
# checks if stackname exists. Returns true if it does, false if not.
    try:

        client = boto3.client('cloudformation',region_name = region)
        response = client.list_stacks(StackStatusFilter=['CREATE_COMPLETE'])
        for stacks in response['StackSummaries']:
            if (stacks['StackName'] == stackname):
                return True
            else:
                return False
    
    except ClientError as e:
        print("[ERROR]",e)
        raise
    except Exception as e:
        print("[ERROR]", e)

def validateregion(region):
# validates passed region name.
    try:

        regionfound = False

        for i in regionslist['Regions']:
            if (i['RegionName'] == region):
                regionfound = True
                break
            
        return regionfound
    
    except ClientError as e:
        print("[ERROR]",e)
        raise
    except Exception as e:
        print("[ERROR]", e)                


def main():
    # main routine


    try:

        parser = argparse.ArgumentParser()
        parser.add_argument("-t","--template-body", default='managed-gdb-cft.yml', type=str, help="CloudFormation template file")
        parser.add_argument("-r","--region-list", type=str,help="List of regions separated by commas, where the stack will be deployed")
        parser.add_argument("-s","--stack-name", type=str, help="CloudFormation Stack Name")
        parser.add_argument("-a","--consent-anonymous-data-collect", type=str, default='yes',help="Opt-in or out of anonymous one time data collection.(yes/no). Only collects region name, creation time, stack name and uuid portion of the stack id (for uniqueness).")

        # process arguments
        args = parser.parse_args()

        # dictionary for region and stack ids
        stack_regions = {}

        global stackname
        stackname = args.stack_name

        http = urllib3.PoolManager()
        
        tepmlatefname = args.template_body
        if not (os.path.isfile(tepmlatefname)):
            print("invalid filename passed for cloudformation template body. Please check the file name and path.")
            exit(1)
        
        #Open and Read the Cloudformation 
        global templateBody
        f = open(tepmlatefname, "r")
        templateBody = f.read()

        # Get the list of regions
        regions = args.region_list.split(',')
        
        # Get all possible regions
        global regionslist
        ec2client = boto3.client('ec2','us-east-1')
        regionslist = ec2client.describe_regions()
        
        # validate all passed region names for correctness
        if not regions:
            print ("Please provide list of regions to build the stack.")
            sys.exit(1)
        else:
            for region in regions:
                
                # regionregex = re.compile(r"^us-[a-z]*-[0-9]{1}")
                # regionmatch  = re.search(regionregex, region)
                if not validateregion(region):
                    print ("Please provide a valid region name in region list. For example: us-east-1. Incorrect region name", region, "was provided.")
                    sys.exit(1)
                elif checkstackname(region):
                    print ("Stack Name", stackname, "already exists in region", region,". Quitting due to stack name conflict. Please choose another stack name.")
                    sys.exit(1)
        
                

        # print (sys.platform)

        stack_building = True

        # Initialize region count
        regionscount=1

        
        # Build stack for all regions
        for region in regions:

            stackid = buildstack (region)
            stackids = stackid.split('/')
            stackid = stackids[2] # split stackid to isolate the uuid portion
            stack_regions[stackid] = region
            regionscount +=1 #count number of regions
            buildtime = datetime.datetime.utcnow().isoformat() + 'Z'
            print("Started building stackid",stackid,"in Region",region, "at:",buildtime)
            
            # This block gathers anonymous data on the stack, if consent is provided. Only data collected is name of the stack, region, timestamp and only UUID part of the stackid.
            payload = {
                    'stack_uuid': stackid,
                    'stack_name': stackname,
                    'stack_region': region,
                    'event_timestamp': datetime.datetime.utcnow().isoformat() + 'Z'
                    
                  }
            if (args.consent_anonymous_data_collect.upper() == 'YES' or args.consent_anonymous_data_collect.upper() == 'Y'):
                r = http.request('POST', "https://ksacb35t5m.execute-api.us-east-1.amazonaws.com/v1/track", body=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'}) 
            
            
        try_count = 1 #Initialize counter to keep track of regions in a loop
                    
        while stack_building:

            waitcount = 1 #Initialize counter for the sleep loop
            for stack in stack_regions:
                                              
                stackid = stack
                stackregion = stack_regions[stack]
                
               
                stack_building = checkstackstatus(stackregion)
                waitcount += 1
                # sleep 5 seconds after looping through allregions, then check all regions again
                if waitcount==regionscount:
                    time.sleep(5)

                # Break the loop only if all regions completed building
                if not stack_building:
                    try_count += 1
                    if try_count==regionscount:
                        break
                    else:
                        stack_building = True

    except ClientError as e:
        print("[ERROR]",e)
        raise
    except Exception as e:
        print("[ERROR]", e)


if __name__ == "__main__":
    main()
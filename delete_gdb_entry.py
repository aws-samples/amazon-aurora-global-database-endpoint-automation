from logging import FATAL
import argparse 
import boto3
from botocore.exceptions import ClientError

def main():
    # Main routine
    
    try:
        #get the cluster name and the region name
        parser=argparse.ArgumentParser()
        parser.add_argument ("-c", "--regional-cluster-name", type=str, help="Name of the regional cluster entry to be deleted")
        parser.add_argument ("-r","--region-name", type=str, default='', help="region name")

        #process arguments
        region = args.region_name
        cluname= args.regional_cluster_name

        #delete the entry from the region
        ddbclient=boto3.client('dynamodb',region_name = region)
        
        dresponse = ddbclient.delete_item(
                    TableName='gdbcnamepair',
                    Key = {
                    'clustername':{'S':cluname}
                            })

    except ClientError as e:
        print(e)
        raise

if __name__ == "__main__":
    main()
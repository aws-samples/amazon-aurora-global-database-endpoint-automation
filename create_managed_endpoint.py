import json
from logging import FATAL
import string
import uuid
import argparse 
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeSerializer,TypeDeserializer
import re
import sys
import datetime
import time

def exists_hz(hzonename):
    # Detects if hosted zone exists. returns True if found, False if not found.
    # If the hosted is public, then the program quits.

    try:
        
        responsehz = dnsclient.list_hosted_zones()

        # Set hosted zone flag
        hostedzonefound = False

        # Return true if Hosted Zone exists
        for hostedzone in responsehz['HostedZones']:
            if ((hostedzone['Name'])==hzonename and hostedzone['Config']['PrivateZone']):
                hostedzonefound = True
            # exists if the Hosted Zone exists and is public
            elif((hostedzone['Name'])==hzonename and not hostedzone['Config']['PrivateZone']):
                print ("Supplied Hosted zone",hzonename,"exists and is a public hosted zone. Please provide either an existsing private hosted zone name, or a hosted zone name that doesn't exist.")
                sys.exit(1)

        return hostedzonefound
    
    except ClientError as e:
        print(e)
        raise

def exists_hz_vpc(hzonename,hzregion,hzvpc):
    # Detects if vpc exists in the hosted zone. returns True if found, false if not found.

    try:
    #get Hosted zone id
        hzid = hosted_zone_id(hzonename)

        
        responsehzvpc = dnsclient.get_hosted_zone(
            Id = hzid
        )

        # Set hosted zone flag
        hostedzonevpcfound = False

        for i in responsehzvpc['VPCs']:
            ergn = (i['VPCRegion'])
            evpc =  (i['VPCId'])
            if (ergn == hzregion and evpc == hzvpc):
                hostedzonevpcfound = True

        return hostedzonevpcfound
    
    except ClientError as e:
        print(e)
        raise

def exists_hz_record (hzonename,recordname):
    # Detects if cname exists in the hosted zone. returns True if found, false if not found.
    
    try:
        hzid = hosted_zone_id(hzonename)
        
        # Add a '.' at the end if it wasn't added
        strlen = len(recordname)
        if recordname[strlen-1]!='.':
            recordname=recordname+'.'

        recordfound = False
        
        
        responsehzr = dnsclient.list_resource_record_sets(
        HostedZoneId=hzid,
        StartRecordName=recordname,
        StartRecordType='CNAME'
        )

        recordfound = False

        for i in responsehzr['ResourceRecordSets']:
            if (i['Name'] == recordname and i['Type']=='CNAME'):
                recordfound = True
        
        return recordfound #return true if record found and false if not
    
    except ClientError as e:
        print(e)
        raise



def create_hosted_zone(hzonename,hzregion,hzvpc):
    #Create a private hosted zone

    try:
        
        responsehzcr = dnsclient.create_hosted_zone(
            Name = hzonename,
            VPC={
                'VPCRegion': hzregion,
                'VPCId': hzvpc
            },
            CallerReference= str(uuid.uuid4()),
            HostedZoneConfig={
                'PrivateZone': True
            }
        )
        
        hzid = responsehzcr['HostedZone']['Id']
        hzparts = hzid.split('/')
        hzid = hzparts[2]
        return hzid
    
    except ClientError as e:
        print(e)
        raise

def update_hosted_zone(hzonename,hzregion,hzvpc):
    # Update hosted zone with vpc associations
    
    try:
        
        hzid = hosted_zone_id(hzonename)
        responsehu = dnsclient.associate_vpc_with_hosted_zone(
        HostedZoneId=hzid,
        VPC={
            'VPCRegion': hzregion,
            'VPCId': hzvpc
        }
        
        )

        return hzid
        
    
    except ClientError as e:
        print(e)
        raise

def create_hosted_zone_record(hzonename,recordname,recordvalue):
    #Update the private hosted zone and create the cname with writer endpoint

    try:
        hzid = hosted_zone_id(hzonename)

        responsedhzrec = dnsclient.change_resource_record_sets(
                        HostedZoneId = hzid,
                        ChangeBatch={
                            "Comment": "Switching endpoint on failover",
                            "Changes": [
                                {
                                    "Action": "CREATE",
                                    "ResourceRecordSet": {
                                        "Name": recordname,
                                        "Type": "CNAME",
                                        "TTL": 1,
                                        "ResourceRecords": [{"Value": recordvalue}]
                                    }
                                }
                            ]
                        }
                    )
                    
        # report cname update status. sucess retuns code 200.
        if (responsedhzrec['ResponseMetadata']['HTTPStatusCode']) == 200:
            print("Cname ",recordname,"Successfully created with endpoint ",recordvalue)
        else:
            print("Error updateing cnname")
    
    except ClientError as e:
        print(e)
        raise

def hosted_zone_id(hzonename):
    # Returns id of the hosted zone passed

    try:
        
        responsehzid = dnsclient.list_hosted_zones()

        for hostedzone in responsehzid['HostedZones']:
            if (hostedzone['Name'])==hzonename:
                hzid = hostedzone['Id']
                hzparts = hzid.split('/')
                hzid = hzparts[2]
        
        return hzid

    except ClientError as e:
        print(e)
        raise

#serializes python dict obj to dynamodb for insertion
def srl_ddb(python_obj: dict) -> dict:
    serializer = TypeSerializer()
    return {
        k: serializer.serialize(v)
        for k, v in python_obj.items()
    } 

#deserializes to dynamodb map data to python dict obj for use
def dsrl_ddb(dynamo_obj: dict) -> dict:
    deserializer = TypeDeserializer()
    return {
        k: deserializer.deserialize(v) 
        for k, v in dynamo_obj.items()
    } 


def make_ddb_entry(cluname,hzid,recordname,region,allregions):
    #Make cluster, hostedzone and region entries in the dynamodb table
    try:
        ddbclient=boto3.client('dynamodb',region_name = region)

        dresponse = ddbclient.put_item(
                    TableName='gdbcnamepair',
                    Item = {
                            "clustername": {
                            "S": cluname
                            },
                            "recordname": {
                            "S": recordname
                            },
                            "hostedzoneid": {
                            "S": hzid
                            },
                            "region": {
                            "S": region
                            },
                            "allregions": {
                            "M": allregions
                            }
                        }
        )
    
        print ("Added entry to the dynamodb table for cluster",cluname)
    except ClientError as e:
        print(e)
        raise

def get_writer_endpoint(cluname):
# returns the writer ednpoint value for  cluster
    try:
        
        responsewe=gdbclient.describe_db_cluster_endpoints(DBClusterIdentifier = cluname) #Get endpoints for the cluster
                        
        # Only process writer endpoint that is currently active
        for j in responsewe ['DBClusterEndpoints']:
            if (j['EndpointType']=="WRITER" and j['Status']=='available'):
                #print("Current writer endpoint: ",j['Endpoint'])
                recordvalue=j['Endpoint']

        return recordvalue

    except ClientError as e:
        print(e)
        raise

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
    # Main routine
    
    try:
        #Get the inputs for 1\cluster name and writer cname entry for that cluster and 2\name of the private hosted zone.
        parser=argparse.ArgumentParser()
        parser.add_argument ("-c", "--cluster-cname-pair", type=str, help="Cluster and writer endpoint pair in '{\"cluname\":\"writer\"}' format")
        parser.add_argument ("-z","--hosted-zone-name", type=str, help="Name of the hosted zone. If one doesn't exist, it will be created")
        parser.add_argument ("-r","--region-list", type=str, default='', help="List of regions separated by commas, where the stack will be deployed")
        parser.add_argument("-sv","--skip-vpc", default=False, action="store_true", help="Skips adding vpcs in the hosted zone, if using an existing hosted zone.")
        

        # Process arguments 
        args=parser.parse_args()

        # ingest cluster name and cname record values passed as argument
        vals = json.loads(args.cluster_cname_pair)
        skipvpc=args.skip_vpc

        # ingest Hosted Zone name passed as argument
        hostedzonename = args.hosted_zone_name
              
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
                if not validateregion(region):
                    print ("Please provide a valid region name in region list. For example: us-east-1. Incorrect region name", region, "was provided.")
                    sys.exit(1)
                    

            
            # for region in regions:
                
            #     regionregex = re.compile(r"^us-[a-z]*-[0-9]{1}")
            #     regionmatch  = re.search(regionregex, region)
                                
            #     if not regionmatch:
                    
                      
        # If the user didn't pass hosted zone in the expected format, fix it by adding a '.' at the end
        strlen = len(hostedzonename)
        if hostedzonename[strlen-1]!='.':
            hostedzonename=hostedzonename+'.'

        # before proceeding make sure that the cname values match the hosted zone domain name.
        for val in vals:
            
            recordname = vals[val]
            recordnameparts = recordname.partition('.')
            recordname1 = str(recordnameparts[2])+'.'
            
            # Check if the hosted zone domain name and the CNAME recrod domain names match, if not exit.
            if (not recordname1 == hostedzonename):
                print("CNAME record",recordname, "does not match the hosted zone",hostedzonename, "Please pass CNAME that match the hosted zone domain name.")
                sys.exit(1)



        for region in regions:

            print("\nProcessing region", region, ":")
            

            # Parse values from the cluster-cname-pair argument. Separate clustername and cname entries.
            for val in vals:
                gdbcluname = val
                recordname = vals[val]

                global gdbclient  
                gdbclient =boto3.client("rds",region_name = region)
                response=gdbclient.describe_global_clusters(GlobalClusterIdentifier = gdbcluname)

                # define dns client globally, since they get used in functions outside of the main function.
         
                global dnsclient 
                dnsclient = boto3.client("route53", region_name = region)

                #find all regions for this global database, and populate in allregion array

                allregions = {}

                for i in response['GlobalClusters'][0]['GlobalClusterMembers']:
                    resourcename = i['DBClusterArn']
                    resourcename = resourcename.split(':')
                    regioname = resourcename[3] #region name is in the 3rd postion
                    cluname = resourcename[6] #clustername is in the 6th position
                    allregions[cluname]=regioname

                #serialize the data 
                gdbobj = srl_ddb(allregions)


                # Loop thorugh each regional cluster member for the provided global cluster
                for i in response['GlobalClusters'][0]['GlobalClusterMembers']:
                    resourcename = i['DBClusterArn']  #This is the ARN
                    resourcename = resourcename.split(':') #Arn splits values with semicolon
                    regioname = resourcename[3] #region name is in the 3rd postion
                    cluname = resourcename[6] #clustername is in the 6th position

                    
                    print("Processing regional cluster", cluname, ":")
                                        

                    # For each writer cluster in the region do following:
                        # 1> If the hosted zone doesn't exists, create it and add the vpc and cname. Make a dynamodb table entry.
                        # 2> If Hosted zone exists, check if current writers vpc is in the hosted zone, if not add it. Then check if the writer cname for the current cluster exists, if not add it. Make a dynamodb table entry.
                        # 3> If hosted zone exists and already has the vpc entry, then add the cname and writer to it. Make a dynamodb table entry.

                    if  (i['IsWriter'] and regioname == region): #Only make entries for current region writer cluster
                        
                        # get the instance name. We need instance name to get the vpc id
                        response1=gdbclient.describe_db_clusters(DBClusterIdentifier = cluname)
                        instancename= (response1['DBClusters'][0]['DBClusterMembers'][0]['DBInstanceIdentifier'])

                        #get vpc name for the instance. We will use this to create\update the private zone
                        response2 = gdbclient.describe_db_instances(DBInstanceIdentifier=instancename)
                        instancevpc = response2['DBInstances'][0]['DBSubnetGroup']['VpcId']

                        # 1> If hosted zone exists 1\check if vpc for current cluster exists, if not, add it 2\next check if writer endpoint exists, if not, add it.
                        if (exists_hz(hostedzonename)):
                            print ("Hosted Zone ", hostedzonename, "already exists. Checking vpcs..")
                            if (exists_hz_vpc(hostedzonename,regioname,instancevpc)):
                                print ("VPC",instancevpc,"Already exists. checking if CNAME exists..")
                                if (exists_hz_record(hostedzonename,recordname)):
                                    print ("CNAME",recordname,"Already exists.")
                                else:
                                    
                                    recordvalue = get_writer_endpoint(cluname) # Get writer endpoint for the cluster
                                    print ("CNAME",recordname,"doesn't exist. Adding CNAME record..")
                                    create_hosted_zone_record(hostedzonename,recordname,recordvalue) # create a cname record in the hosted zone for the writer endpoint
                                    hzid = hosted_zone_id(hostedzonename) #get hosted zone id
                                    make_ddb_entry(cluname,hzid,recordname,regioname,gdbobj) # Add dynamodb entry
                            else:
                                if (skipvpc == False):
                                    print ("Vpc",instancevpc," doesn't exist. Adding vpc..")
                                    hzid = update_hosted_zone(hostedzonename,regioname,instancevpc)
                                    make_ddb_entry(cluname,hzid,recordname,regioname,gdbobj) #Make ddb entry. This should only work from the calling region.
                                else:
                                    print ("Vpc",instancevpc," doesn't exist. But skipping due to skip vpc flag.") 
                                if (exists_hz_record(hostedzonename,recordname)):
                                    print ("CNAME",recordname,"Already exists.")
                                else:
                                    
                                    recordvalue = get_writer_endpoint(cluname) # Get writer endpoint for the cluster
                                    print ("CNAME",recordname,"doesn't exist. Adding CNAME record for Primary region cluster", cluname)
                                    create_hosted_zone_record(hostedzonename,recordname,recordvalue) # create a cname record in the hosted zone for the writer endpoint
                                    hzid = hosted_zone_id(hostedzonename) #get hosted zone id
                                    make_ddb_entry(cluname,hzid,recordname,regioname,gdbobj) # Add dynamodb entry
                        else:
                            print ("Hosted Zone doesn't exists. Creating ",hostedzonename)
                            hzid = create_hosted_zone(hostedzonename,regioname,instancevpc)
                            
                            make_ddb_entry(cluname,hzid,recordname,regioname,gdbobj) #Make ddb entry. This should only work from the calling region.

                            recordvalue = get_writer_endpoint(cluname) # Get writer endpoint for the cluster
                            print ("Adding CNAME record ", recordname,"for for Primary region cluster ",cluname)
                            create_hosted_zone_record(hostedzonename,recordname,recordvalue) # create a cname record in the hosted zone for the writer endpoint

                        # For each reader cluster in the region do following:
                            # 1> If the hosted zone doesn't exists, create it and add the vpc and cname. Make a dynamodb table entry.
                            # 2> If Hosted zone exists, check if current reader vpc is in the hosted zone, if not add it. Make a dynamodb table entry.
                            # 3> If neither condition is true just make  a dynamodb table entry.

            
                    elif  (i['IsWriter'] == False and regioname == region): #Only make entries for current region reader cluster
                        
                        # get the instance name. We need instance name to get the vpc id
                        response1=gdbclient.describe_db_clusters(DBClusterIdentifier = cluname)
                        instancename= (response1['DBClusters'][0]['DBClusterMembers'][0]['DBInstanceIdentifier'])

                        #get vpc name for the instance. We will use this to create\update the private zone
                        response2 = gdbclient.describe_db_instances(DBInstanceIdentifier=instancename)
                        instancevpc = response2['DBInstances'][0]['DBSubnetGroup']['VpcId']

                        if (exists_hz(hostedzonename)):
                            print ("Hosted Zone ", hostedzonename, "already exists. Checking vpcs..")
                            if (exists_hz_vpc(hostedzonename,regioname,instancevpc)):
                                print ("VPC ",instancevpc,"Already exists for secondary region cluster ", cluname)
                                
                                hzid = hosted_zone_id(hostedzonename) #get hosted zone id
                                make_ddb_entry(cluname,hzid,recordname,regioname,gdbobj) # Add dynamodb entry
                                    
                            else:
                                if (skipvpc == False):
                                    print ("VPC",instancevpc," doesn't exist in the hosted zone. Adding vpc..")
                                    hzid = update_hosted_zone(hostedzonename,regioname,instancevpc)
                                    make_ddb_entry(cluname,hzid,recordname,regioname,gdbobj) #Make ddb entry. This should only work from the calling region.
                                else:
                                    print ("Vpc",instancevpc," doesn't exist. But skipping due to skip vpc flag.") 

                        else:
                            print ("Hosted Zone doesn't exists. Creating ",hostedzonename)
                            hzid = create_hosted_zone(hostedzonename,regioname,instancevpc)
                            make_ddb_entry(cluname,hzid,recordname,regioname,gdbobj) #Make ddb entry. This should only work from the calling region.
                    else:
                        print ("No entries made for this cluster. Cluster is not in the current region.")
    
    except ClientError as e:
        print(e)
        raise

if __name__ == "__main__":
    main()
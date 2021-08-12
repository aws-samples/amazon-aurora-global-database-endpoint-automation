# Automated endpoint management for Amazon Aurora Global Database

This solution includes a cloudformation template and a python script. This document will describe how to use this solution. 

## Architecture
![Solution Architecture](img/architecture.png)

```bash
.
├── README.MD                   <-- This readme instructions file
├── managed-gdb-cft.yaml        <-- Cloudformation template
├── create_managed_endpoint.py  <-- source code for deploying the solution

```

## Requirements

* AWS CLI already configured with Administrator permission
* Python 3.8
* [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#installation)
* AWS Account with an Amazon Aurora global database with at least 2 regions. 

## Set up

Follow the instructions below in order to deploy from this repository:


1. Clone the repo onto your local development machine:

 ```bash 
 git clone https://github.com/aws-samples/amazon-aurora-global-database-endpoint-automation.git
 ```


>**_NOTE:_**
You will have to execute the following commands multiple times, passing the region name every time. You will do this for all regions of your global database. For example if your global database is deployed in us-east-1 and us-west-2, then you will have to execute the commands twice with the region parameter as us-east-1 and then again with region parameter as us-west-2. 


 2. In the root directory, from the command line, run following command, for each region of the global database. 

 ```bash
 aws cloudformation create-stack --capabilities CAPABILITY_NAMED_IAM --template-body file://managed-gdb-cft.yml --stack-name <stackname> --region <region name>

 example:
 aws cloudformation create-stack --capabilities CAPABILITY_NAMED_IAM --template-body file://managed-gdb-cft.yml --stack-name managed-gdb --region us-east-1
 
 ```
This command will execute the cloudformation template and create all required resources in the region.


 3. Once the cloudformation finishes building resources in all regions, execute the following command, for each region of the  global database.

 ```bash
 python3 create_hosted_zone.py --cluster-cname-pair='{"<global database clustername>":"<desired writer endpoint >" [,"<global database clustername>":"<desired writer endpoint>"}' --hosted-zone-name=<hosted zone name> --region<aws region name>

 example:
 python3 create_hosted_zone.py --cluster-cname-pair='{"gdb-cluster1":"writer1.myhostedzone.com" ,"gdb-cluster2":"writer2.myhostedzone.com"}' --hosted-zone-name=writer2.myhostedzone.com --region us-east-1
 ```

**What do these parameters mean?**  
    
The script takes following parameters:  

**-c OR --cluster-cname-pair** : Cluster and writer endpoint pair in '{\"cluname\":\"writer\"}' format. **(Required)**  
**-z OR --hosted-zone-name** :  Name of the hosted zone. If one doesn't exist, it will be created. **(Required)**  
**-r OR --region** : Region Name. If no region is provided, default region is used. **(Optional)**  
**-sv OR --skip-vpc** : Skips adding vpcs in the hosted zone, if using an existing hosted zone. **(Optional)**  

If you made any mistakes, no worries. You can just re-run it. The script is idempotent. And when you are ready to add a new global cluster, you can just re-run it with the new global-cluster and CNAME pair. 

## What resources will this solution create?

After deploying this solution, you will see two types of resources:

 1. **Global resources:**
 * **Private Hosted Zone (Route 53)**: A private hosted Zone will be created based on the values you passed.
 * **CNAME**: A CNAME will be created inside the hosted zone based on the parameters you passed.

 2. **Local resources created per region:**
* **IAM Role**: An IAM role will be created so the Lambda function can assume this role while executing.
* **Lambda function**: This is the workhorse of the solution. This lambda will be fired on global database failover completion event, and will update the cname.
* **DynamoDB table**: A dynamDB table named `gdbcnamepair` will be created. This table keeps track of the clusters that will be managed by this solution.
* **EventBridge Rule**: This EventBridge Rule will be fired when a global database completes failover in the region. This rule has the Lambda function as it's target.

## Current Limitations

* **Partial SSL Support** - Since the solution uses a Route 53 CNAME, the SSL certificate will not be able to validate the aurora servername. For example pgsql client [verify-full](https://www.postgresql.org/docs/9.1/libpq-ssl.html) or mysql client [ssl-verify-server-cert](https://dev.mysql.com/doc/refman/5.7/en/connection-options.html#option_general_ssl-verify-server-cert) will fail to validate server identity.
* **Only supports [Managed planned failover](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-disaster-recovery.html#aurora-global-database-disaster-recovery.managed-failover)** - If you do a manual failover by braking the global database cluster and then promoting the secondary region cluster tp primary (detach and promote). This solution will not be able to detect that condition.


## License Summary
This sample code is made available under a modified MIT license. See the LICENSE file.
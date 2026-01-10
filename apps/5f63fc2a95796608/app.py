import boto3
import os
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DeploymentStrategy(Enum):
    """Deployment strategies for multi-tier applications."""
    BLUE_GREEN = "blue_green"
    ROLLING = "rolling"
    CANARY = "canary"


@dataclass
class ApplicationTier:
    """Represents an application tier configuration."""
    name: str
    instance_type: str
    min_instances: int
    max_instances: int
    subnet_type: str
    security_group_name: str
    user_data_script: Optional[str] = None


@dataclass
class NetworkInfrastructure:
    """Represents the network infrastructure state."""
    vpc_id: str
    public_subnets: Dict[str, str]
    private_subnets: Dict[str, str]
    nat_gateways: Dict[str, str]
    internet_gateway_id: str
    route_tables: Dict[str, str]


class MultiTierApplicationDeployer:
    """Manages deployment of multi-tier applications across VPC infrastructure."""
    
    def __init__(self, endpoint_url: str = None):
        """Initialize the application deployer.
        
        Args:
            endpoint_url: AWS endpoint URL (for LocalStack)
        """
        self.endpoint_url = endpoint_url or os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
        self.ec2_client = boto3.client(
            "ec2",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        self.ec2_resource = boto3.resource(
            "ec2",
            endpoint_url=self.endpoint_url,
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test"
        )
        
        # Application tiers configuration
        self.application_tiers = {
            "web": ApplicationTier(
                name="web-tier",
                instance_type="t3.micro",
                min_instances=2,
                max_instances=4,
                subnet_type="public",
                security_group_name="web-sg",
                user_data_script=self._get_web_tier_user_data()
            ),
            "app": ApplicationTier(
                name="app-tier",
                instance_type="t3.small",
                min_instances=2,
                max_instances=6,
                subnet_type="private",
                security_group_name="app-sg",
                user_data_script=self._get_app_tier_user_data()
            ),
            "db": ApplicationTier(
                name="db-tier",
                instance_type="t3.medium",
                min_instances=1,
                max_instances=2,
                subnet_type="private",
                security_group_name="db-sg",
                user_data_script=self._get_db_tier_user_data()
            )
        }
    
    def _get_web_tier_user_data(self) -> str:
        """Get user data script for web tier instances."""
        return '''
#!/bin/bash
yum update -y
yum install -y nginx
systemctl start nginx
systemctl enable nginx

# Configure nginx as load balancer
cat > /etc/nginx/nginx.conf << 'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    upstream app_servers {
        server 10.0.10.10:8080;
        server 10.0.20.10:8080;
    }
    
    server {
        listen 80;
        location / {
            proxy_pass http://app_servers;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
EOF

systemctl restart nginx
'''
    
    def _get_app_tier_user_data(self) -> str:
        """Get user data script for application tier instances."""
        return '''
#!/bin/bash
yum update -y
yum install -y docker
systemctl start docker
systemctl enable docker

# Run sample application
docker run -d -p 8080:8080 --name app --restart always nginx:alpine
'''
    
    def _get_db_tier_user_data(self) -> str:
        """Get user data script for database tier instances."""
        return '''
#!/bin/bash
yum update -y
yum install -y postgresql-server postgresql-contrib
postgresql-setup initdb
systemctl start postgresql
systemctl enable postgresql
'''
    
    def discover_infrastructure(self) -> NetworkInfrastructure:
        """Discover existing VPC infrastructure created by Terraform.
        
        Returns:
            NetworkInfrastructure object with discovered resources
        """
        logger.info("Discovering VPC infrastructure...")
        
        # Find VPC created by Terraform
        vpcs = self.ec2_client.describe_vpcs(
            Filters=[
                {'Name': 'tag:Name', 'Values': ['*']},
                {'Name': 'state', 'Values': ['available']}
            ]
        )['Vpcs']
        
        if not vpcs:
            raise ValueError("No VPC found. Ensure Terraform infrastructure is deployed.")
        
        vpc_id = vpcs[0]['VpcId']
        logger.info(f"Found VPC: {vpc_id}")
        
        # Discover subnets
        subnets = self.ec2_client.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )['Subnets']
        
        public_subnets = {}
        private_subnets = {}
        
        for subnet in subnets:
            subnet_id = subnet['SubnetId']
            tags = {tag['Key']: tag['Value'] for tag in subnet.get('Tags', [])}
            access_type = tags.get('access_type', 'unknown')
            subnet_name = tags.get('Name', subnet_id)
            
            if access_type == 'public':
                public_subnets[subnet_name] = subnet_id
            elif access_type == 'private':
                private_subnets[subnet_name] = subnet_id
        
        # Discover NAT gateways
        nat_gateways_response = self.ec2_client.describe_nat_gateways(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        nat_gateways = {gw['NatGatewayId']: gw['SubnetId'] for gw in nat_gateways_response['NatGateways']}
        
        # Discover Internet Gateway
        igws = self.ec2_client.describe_internet_gateways(
            Filters=[{'Name': 'attachment.vpc-id', 'Values': [vpc_id]}]
        )['InternetGateways']
        internet_gateway_id = igws[0]['InternetGatewayId'] if igws else None
        
        # Discover Route Tables
        route_tables = self.ec2_client.describe_route_tables(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )['RouteTables']
        rt_dict = {rt['RouteTableId']: rt for rt in route_tables}
        
        infrastructure = NetworkInfrastructure(
            vpc_id=vpc_id,
            public_subnets=public_subnets,
            private_subnets=private_subnets,
            nat_gateways=nat_gateways,
            internet_gateway_id=internet_gateway_id,
            route_tables=rt_dict
        )
        
        logger.info(f"Discovered infrastructure: {len(public_subnets)} public subnets, {len(private_subnets)} private subnets")
        return infrastructure
    
    def create_security_groups(self, infrastructure: NetworkInfrastructure) -> Dict[str, str]:
        """Create security groups for application tiers.
        
        Args:
            infrastructure: Discovered network infrastructure
            
        Returns:
            Dictionary mapping security group names to IDs
        """
        logger.info("Creating security groups...")
        security_groups = {}
        
        # Web tier security group
        web_sg = self.ec2_client.create_security_group(
            GroupName='web-security-group',
            Description='Security group for web tier',
            VpcId=infrastructure.vpc_id
        )
        web_sg_id = web_sg['GroupId']
        security_groups['web-sg'] = web_sg_id
        
        # Add inbound rules for web tier
        self.ec2_client.authorize_security_group_ingress(
            GroupId=web_sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 80,
                    'ToPort': 80,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 443,
                    'ToPort': 443,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
                }
            ]
        )
        
        # App tier security group
        app_sg = self.ec2_client.create_security_group(
            GroupName='app-security-group',
            Description='Security group for application tier',
            VpcId=infrastructure.vpc_id
        )
        app_sg_id = app_sg['GroupId']
        security_groups['app-sg'] = app_sg_id
        
        # Add inbound rules for app tier
        self.ec2_client.authorize_security_group_ingress(
            GroupId=app_sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 8080,
                    'ToPort': 8080,
                    'UserIdGroupPairs': [{'GroupId': web_sg_id}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
                }
            ]
        )
        
        # DB tier security group
        db_sg = self.ec2_client.create_security_group(
            GroupName='db-security-group',
            Description='Security group for database tier',
            VpcId=infrastructure.vpc_id
        )
        db_sg_id = db_sg['GroupId']
        security_groups['db-sg'] = db_sg_id
        
        # Add inbound rules for db tier
        self.ec2_client.authorize_security_group_ingress(
            GroupId=db_sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 5432,
                    'ToPort': 5432,
                    'UserIdGroupPairs': [{'GroupId': app_sg_id}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
                }
            ]
        )
        
        logger.info(f"Created {len(security_groups)} security groups")
        return security_groups
    
    def deploy_application_tier(self, tier_name: str, infrastructure: NetworkInfrastructure, 
                              security_groups: Dict[str, str]) -> List[str]:
        """Deploy instances for a specific application tier.
        
        Args:
            tier_name: Name of the tier to deploy ('web', 'app', 'db')
            infrastructure: Network infrastructure
            security_groups: Security group mappings
            
        Returns:
            List of instance IDs
        """
        if tier_name not in self.application_tiers:
            raise ValueError(f"Unknown tier: {tier_name}")
        
        tier = self.application_tiers[tier_name]
        logger.info(f"Deploying {tier_name} tier with {tier.min_instances} instances")
        
        # Select appropriate subnets
        if tier.subnet_type == "public":
            available_subnets = list(infrastructure.public_subnets.values())
        else:
            available_subnets = list(infrastructure.private_subnets.values())
        
        if not available_subnets:
            raise ValueError(f"No {tier.subnet_type} subnets available for {tier_name} tier")
        
        # Get Amazon Linux 2 AMI (this is a mock ID for LocalStack)
        ami_id = "ami-0abcdef1234567890"  # LocalStack accepts any AMI ID
        
        # Launch instances across multiple AZs for high availability
        instance_ids = []
        security_group_id = security_groups[tier.security_group_name]
        
        for i in range(tier.min_instances):
            subnet_id = available_subnets[i % len(available_subnets)]
            
            response = self.ec2_client.run_instances(
                ImageId=ami_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=tier.instance_type,
                SecurityGroupIds=[security_group_id],
                SubnetId=subnet_id,
                UserData=tier.user_data_script or "",
                TagSpecifications=[
                    {
                        'ResourceType': 'instance',
                        'Tags': [
                            {'Key': 'Name', 'Value': f'{tier.name}-{i+1}'},
                            {'Key': 'Tier', 'Value': tier_name},
                            {'Key': 'Environment', 'Value': 'production'}
                        ]
                    }
                ]
            )
            
            instance_id = response['Instances'][0]['InstanceId']
            instance_ids.append(instance_id)
            logger.info(f"Launched instance {instance_id} in subnet {subnet_id}")
        
        return instance_ids
    
    def deploy_full_application(self, strategy: DeploymentStrategy = DeploymentStrategy.ROLLING) -> Dict[str, List[str]]:
        """Deploy a complete multi-tier application.
        
        Args:
            strategy: Deployment strategy to use
            
        Returns:
            Dictionary mapping tier names to instance IDs
        """
        logger.info(f"Starting full application deployment with {strategy.value} strategy")
        
        # Discover infrastructure
        infrastructure = self.discover_infrastructure()
        
        # Create security groups
        security_groups = self.create_security_groups(infrastructure)
        
        # Deploy tiers in order (DB -> App -> Web)
        deployment_order = ['db', 'app', 'web']
        deployed_instances = {}
        
        for tier_name in deployment_order:
            logger.info(f"Deploying {tier_name} tier...")
            
            if strategy == DeploymentStrategy.ROLLING:
                # Deploy instances one by one with health checks
                instances = self.deploy_application_tier(tier_name, infrastructure, security_groups)
                deployed_instances[tier_name] = instances
                
                # Wait for instances to be running
                self.wait_for_instances_running(instances)
                
                # Simulate health check delay
                time.sleep(2)
                
            elif strategy == DeploymentStrategy.BLUE_GREEN:
                # Deploy all instances at once
                instances = self.deploy_application_tier(tier_name, infrastructure, security_groups)
                deployed_instances[tier_name] = instances
            
            logger.info(f"Deployed {len(deployed_instances[tier_name])} instances for {tier_name} tier")
        
        logger.info("Full application deployment completed")
        return deployed_instances
    
    def wait_for_instances_running(self, instance_ids: List[str], timeout: int = 300) -> bool:
        """Wait for instances to reach running state.
        
        Args:
            instance_ids: List of instance IDs to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if all instances are running, False if timeout
        """
        logger.info(f"Waiting for {len(instance_ids)} instances to reach running state...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            response = self.ec2_client.describe_instances(InstanceIds=instance_ids)
            
            all_running = True
            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    if instance['State']['Name'] != 'running':
                        all_running = False
                        break
                if not all_running:
                    break
            
            if all_running:
                logger.info("All instances are now running")
                return True
            
            time.sleep(5)
        
        logger.warning(f"Timeout waiting for instances to reach running state")
        return False
    
    def validate_network_connectivity(self, infrastructure: NetworkInfrastructure) -> Dict[str, bool]:
        """Validate network connectivity and routing.
        
        Args:
            infrastructure: Network infrastructure to validate
            
        Returns:
            Dictionary with validation results
        """
        logger.info("Validating network connectivity...")
        
        validation_results = {
            'vpc_exists': bool(infrastructure.vpc_id),
            'public_subnets_exist': len(infrastructure.public_subnets) > 0,
            'private_subnets_exist': len(infrastructure.private_subnets) > 0,
            'nat_gateways_exist': len(infrastructure.nat_gateways) > 0,
            'internet_gateway_exists': bool(infrastructure.internet_gateway_id),
            'route_tables_exist': len(infrastructure.route_tables) > 0
        }
        
        # Validate route table configurations
        public_route_to_igw = False
        private_route_to_nat = False
        
        for rt_id, rt_info in infrastructure.route_tables.items():
            routes = rt_info.get('Routes', [])
            
            for route in routes:
                # Check for public subnet routes to Internet Gateway
                if (route.get('DestinationCidrBlock') == '0.0.0.0/0' and 
                    'GatewayId' in route and route['GatewayId'].startswith('igw-')):
                    public_route_to_igw = True
                
                # Check for private subnet routes to NAT Gateway
                if (route.get('DestinationCidrBlock') == '0.0.0.0/0' and 
                    'NatGatewayId' in route):
                    private_route_to_nat = True
        
        validation_results['public_internet_routing'] = public_route_to_igw
        validation_results['private_nat_routing'] = private_route_to_nat
        
        # Overall health check
        validation_results['overall_health'] = all(validation_results.values())
        
        logger.info(f"Network validation completed. Overall health: {validation_results['overall_health']}")
        return validation_results
    
    def cleanup_application(self, instance_ids: List[str]) -> bool:
        """Clean up deployed application instances.
        
        Args:
            instance_ids: List of instance IDs to terminate
            
        Returns:
            True if cleanup successful
        """
        if not instance_ids:
            return True
        
        logger.info(f"Cleaning up {len(instance_ids)} instances...")
        
        try:
            self.ec2_client.terminate_instances(InstanceIds=instance_ids)
            
            # Wait for instances to terminate
            start_time = time.time()
            timeout = 180
            
            while time.time() - start_time < timeout:
                response = self.ec2_client.describe_instances(InstanceIds=instance_ids)
                
                all_terminated = True
                for reservation in response['Reservations']:
                    for instance in reservation['Instances']:
                        state = instance['State']['Name']
                        if state not in ['terminated', 'terminating']:
                            all_terminated = False
                            break
                
                if all_terminated:
                    logger.info("All instances have been terminated")
                    return True
                
                time.sleep(5)
            
            logger.warning("Timeout waiting for instance termination")
            return False
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return False


def main():
    """Main function for testing the application deployment."""
    deployer = MultiTierApplicationDeployer()
    
    try:
        # Deploy full application
        deployed_instances = deployer.deploy_full_application(DeploymentStrategy.ROLLING)
        print(f"Deployed instances: {deployed_instances}")
        
        # Validate infrastructure
        infrastructure = deployer.discover_infrastructure()
        validation_results = deployer.validate_network_connectivity(infrastructure)
        print(f"Validation results: {validation_results}")
        
        # Cleanup
        all_instances = []
        for tier_instances in deployed_instances.values():
            all_instances.extend(tier_instances)
        
        deployer.cleanup_application(all_instances)
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
        raise


if __name__ == "__main__":
    main()
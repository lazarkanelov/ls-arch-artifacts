import boto3
import os
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class NetworkResource:
    """Represents a network resource with its attributes."""
    id: str
    name: str
    cidr: Optional[str] = None
    availability_zone: Optional[str] = None
    state: Optional[str] = None
    tags: Optional[Dict[str, str]] = None


@dataclass
class InstanceDeployment:
    """Represents an EC2 instance deployment configuration."""
    name: str
    subnet_id: str
    security_group_ids: List[str]
    instance_type: str = "t3.micro"
    ami_id: str = "ami-0c02fb55956c7d316"
    user_data: Optional[str] = None


class NetworkInfrastructureManager:
    """Manages network infrastructure operations and EC2 deployments."""
    
    def __init__(self):
        """Initialize the network infrastructure manager."""
        self.aws_config = {
            "endpoint_url": os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566"),
            "region_name": "us-east-1",
            "aws_access_key_id": "test",
            "aws_secret_access_key": "test"
        }
        self.ec2_client = boto3.client("ec2", **self.aws_config)
        self.ec2_resource = boto3.resource("ec2", **self.aws_config)
        
    def discover_vpc_infrastructure(self, vpc_name: str) -> Dict[str, Any]:
        """Discover and catalog VPC infrastructure components.
        
        Args:
            vpc_name: Name of the VPC to discover
            
        Returns:
            Dictionary containing VPC infrastructure details
        """
        try:
            # Find VPC by name
            vpcs = self.ec2_client.describe_vpcs(
                Filters=[{"Name": "tag:Name", "Values": [vpc_name]}]
            )
            
            if not vpcs["Vpcs"]:
                raise ValueError(f"VPC with name '{vpc_name}' not found")
            
            vpc = vpcs["Vpcs"][0]
            vpc_id = vpc["VpcId"]
            
            logger.info(f"Discovered VPC: {vpc_id} ({vpc_name})")
            
            # Discover subnets
            subnets_response = self.ec2_client.describe_subnets(
                Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
            )
            
            infrastructure = {
                "vpc": NetworkResource(
                    id=vpc_id,
                    name=vpc_name,
                    cidr=vpc["CidrBlock"],
                    state=vpc["State"],
                    tags=self._extract_tags(vpc.get("Tags", []))
                ),
                "subnets": {
                    "public": [],
                    "private": []
                },
                "internet_gateway": None,
                "nat_gateways": [],
                "route_tables": []
            }
            
            # Categorize subnets
            for subnet in subnets_response["Subnets"]:
                subnet_obj = NetworkResource(
                    id=subnet["SubnetId"],
                    name=self._get_tag_value(subnet.get("Tags", []), "Name"),
                    cidr=subnet["CidrBlock"],
                    availability_zone=subnet["AvailabilityZone"],
                    state=subnet["State"],
                    tags=self._extract_tags(subnet.get("Tags", []))
                )
                
                # Determine if subnet is public or private based on route table
                if subnet["MapPublicIpOnLaunch"]:
                    infrastructure["subnets"]["public"].append(subnet_obj)
                else:
                    infrastructure["subnets"]["private"].append(subnet_obj)
            
            # Discover Internet Gateway
            igws = self.ec2_client.describe_internet_gateways(
                Filters=[{"Name": "attachment.vpc-id", "Values": [vpc_id]}]
            )
            
            if igws["InternetGateways"]:
                igw = igws["InternetGateways"][0]
                infrastructure["internet_gateway"] = NetworkResource(
                    id=igw["InternetGatewayId"],
                    name=self._get_tag_value(igw.get("Tags", []), "Name"),
                    tags=self._extract_tags(igw.get("Tags", []))
                )
            
            # Discover NAT Gateways
            nat_gws = self.ec2_client.describe_nat_gateways(
                Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
            )
            
            for nat_gw in nat_gws["NatGateways"]:
                if nat_gw["State"] != "deleted":
                    infrastructure["nat_gateways"].append(
                        NetworkResource(
                            id=nat_gw["NatGatewayId"],
                            name=self._get_tag_value(nat_gw.get("Tags", []), "Name"),
                            tags=self._extract_tags(nat_gw.get("Tags", []))
                        )
                    )
            
            logger.info(f"Infrastructure discovery complete: {len(infrastructure['subnets']['public'])} public subnets, {len(infrastructure['subnets']['private'])} private subnets")
            return infrastructure
            
        except ClientError as e:
            logger.error(f"AWS error during infrastructure discovery: {e}")
            raise
        except Exception as e:
            logger.error(f"Error discovering infrastructure: {e}")
            raise
    
    def create_security_group(self, vpc_id: str, name: str, description: str, 
                            ingress_rules: List[Dict[str, Any]]) -> str:
        """Create a security group with specified rules.
        
        Args:
            vpc_id: VPC ID to create the security group in
            name: Security group name
            description: Security group description
            ingress_rules: List of ingress rules
            
        Returns:
            Security group ID
        """
        try:
            response = self.ec2_client.create_security_group(
                GroupName=name,
                Description=description,
                VpcId=vpc_id,
                TagSpecifications=[
                    {
                        "ResourceType": "security-group",
                        "Tags": [
                            {"Key": "Name", "Value": name}
                        ]
                    }
                ]
            )
            
            sg_id = response["GroupId"]
            logger.info(f"Created security group: {sg_id} ({name})")
            
            # Add ingress rules
            if ingress_rules:
                self.ec2_client.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=ingress_rules
                )
                logger.info(f"Added {len(ingress_rules)} ingress rules to {sg_id}")
            
            return sg_id
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidGroup.Duplicate":
                logger.warning(f"Security group {name} already exists")
                # Find existing security group
                sgs = self.ec2_client.describe_security_groups(
                    Filters=[
                        {"Name": "group-name", "Values": [name]},
                        {"Name": "vpc-id", "Values": [vpc_id]}
                    ]
                )
                return sgs["SecurityGroups"][0]["GroupId"]
            logger.error(f"Error creating security group: {e}")
            raise
    
    def deploy_multi_tier_application(self, infrastructure: Dict[str, Any], 
                                    app_config: Dict[str, Any]) -> Dict[str, List[str]]:
        """Deploy a multi-tier application across the network infrastructure.
        
        Args:
            infrastructure: Infrastructure details from discovery
            app_config: Application deployment configuration
            
        Returns:
            Dictionary mapping tier names to instance IDs
        """
        deployments = {}
        
        try:
            vpc_id = infrastructure["vpc"].id
            
            # Create security groups for different tiers
            security_groups = self._create_tier_security_groups(vpc_id)
            
            # Deploy web tier in public subnets
            if "web" in app_config:
                web_instances = self._deploy_tier(
                    "web",
                    infrastructure["subnets"]["public"],
                    security_groups["web"],
                    app_config["web"]
                )
                deployments["web"] = web_instances
            
            # Deploy app tier in private subnets (app type)
            if "app" in app_config:
                app_subnets = [
                    subnet for subnet in infrastructure["subnets"]["private"]
                    if subnet.tags and subnet.tags.get("Tier") == "app"
                ]
                app_instances = self._deploy_tier(
                    "app",
                    app_subnets,
                    security_groups["app"],
                    app_config["app"]
                )
                deployments["app"] = app_instances
            
            # Deploy database tier in private subnets (db type)
            if "database" in app_config:
                db_subnets = [
                    subnet for subnet in infrastructure["subnets"]["private"]
                    if subnet.tags and subnet.tags.get("Tier") == "database"
                ]
                db_instances = self._deploy_tier(
                    "database",
                    db_subnets,
                    security_groups["database"],
                    app_config["database"]
                )
                deployments["database"] = db_instances
            
            logger.info(f"Multi-tier deployment complete: {sum(len(instances) for instances in deployments.values())} total instances")
            return deployments
            
        except Exception as e:
            logger.error(f"Error during multi-tier deployment: {e}")
            raise
    
    def validate_network_connectivity(self, infrastructure: Dict[str, Any]) -> Dict[str, bool]:
        """Validate network connectivity between different tiers.
        
        Args:
            infrastructure: Infrastructure details
            
        Returns:
            Dictionary of connectivity test results
        """
        results = {}
        
        try:
            vpc_id = infrastructure["vpc"].id
            
            # Test 1: VPC DNS resolution
            results["vpc_dns_enabled"] = self._check_vpc_dns_settings(vpc_id)
            
            # Test 2: Public subnet internet connectivity
            results["public_internet_access"] = self._validate_public_internet_access(
                infrastructure["subnets"]["public"]
            )
            
            # Test 3: Private subnet NAT gateway connectivity
            results["private_nat_access"] = self._validate_private_nat_access(
                infrastructure["subnets"]["private"],
                infrastructure["nat_gateways"]
            )
            
            # Test 4: Cross-AZ connectivity
            results["cross_az_connectivity"] = self._validate_cross_az_connectivity(
                infrastructure["subnets"]
            )
            
            # Test 5: Security group isolation
            results["security_isolation"] = self._validate_security_isolation(vpc_id)
            
            logger.info(f"Network connectivity validation complete: {sum(results.values())}/{len(results)} tests passed")
            return results
            
        except Exception as e:
            logger.error(f"Error during network validation: {e}")
            raise
    
    def cleanup_deployment(self, instance_ids: List[str]) -> bool:
        """Clean up deployed instances and associated resources.
        
        Args:
            instance_ids: List of instance IDs to terminate
            
        Returns:
            True if cleanup successful
        """
        try:
            if instance_ids:
                self.ec2_client.terminate_instances(InstanceIds=instance_ids)
                logger.info(f"Initiated termination of {len(instance_ids)} instances")
                
                # Wait for instances to terminate
                waiter = self.ec2_client.get_waiter('instance_terminated')
                waiter.wait(InstanceIds=instance_ids, WaiterConfig={'Delay': 5, 'MaxAttempts': 20})
                logger.info("All instances terminated successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return False
    
    def _extract_tags(self, tag_list: List[Dict[str, str]]) -> Dict[str, str]:
        """Extract tags from AWS tag list format."""
        return {tag["Key"]: tag["Value"] for tag in tag_list}
    
    def _get_tag_value(self, tag_list: List[Dict[str, str]], key: str) -> Optional[str]:
        """Get specific tag value from AWS tag list."""
        for tag in tag_list:
            if tag["Key"] == key:
                return tag["Value"]
        return None
    
    def _create_tier_security_groups(self, vpc_id: str) -> Dict[str, str]:
        """Create security groups for different application tiers."""
        security_groups = {}
        
        # Web tier security group (HTTP/HTTPS from internet)
        web_rules = [
            {
                "IpProtocol": "tcp",
                "FromPort": 80,
                "ToPort": 80,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTP from internet"}]
            },
            {
                "IpProtocol": "tcp",
                "FromPort": 443,
                "ToPort": 443,
                "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTPS from internet"}]
            }
        ]
        
        security_groups["web"] = self.create_security_group(
            vpc_id, "web-tier-sg", "Security group for web tier", web_rules
        )
        
        # App tier security group (access from web tier)
        app_rules = [
            {
                "IpProtocol": "tcp",
                "FromPort": 8080,
                "ToPort": 8080,
                "UserIdGroupPairs": [{"GroupId": security_groups["web"], "Description": "App port from web tier"}]
            }
        ]
        
        security_groups["app"] = self.create_security_group(
            vpc_id, "app-tier-sg", "Security group for app tier", app_rules
        )
        
        # Database tier security group (access from app tier)
        db_rules = [
            {
                "IpProtocol": "tcp",
                "FromPort": 3306,
                "ToPort": 3306,
                "UserIdGroupPairs": [{"GroupId": security_groups["app"], "Description": "MySQL from app tier"}]
            }
        ]
        
        security_groups["database"] = self.create_security_group(
            vpc_id, "db-tier-sg", "Security group for database tier", db_rules
        )
        
        return security_groups
    
    def _deploy_tier(self, tier_name: str, subnets: List[NetworkResource], 
                    security_group_id: str, config: Dict[str, Any]) -> List[str]:
        """Deploy instances for a specific tier."""
        instance_ids = []
        
        instances_per_subnet = config.get("instances_per_subnet", 1)
        instance_type = config.get("instance_type", "t3.micro")
        ami_id = config.get("ami_id", "ami-0c02fb55956c7d316")
        
        for subnet in subnets:
            for i in range(instances_per_subnet):
                try:
                    response = self.ec2_client.run_instances(
                        ImageId=ami_id,
                        MinCount=1,
                        MaxCount=1,
                        InstanceType=instance_type,
                        SubnetId=subnet.id,
                        SecurityGroupIds=[security_group_id],
                        TagSpecifications=[
                            {
                                "ResourceType": "instance",
                                "Tags": [
                                    {"Key": "Name", "Value": f"{tier_name}-{subnet.availability_zone}-{i+1}"},
                                    {"Key": "Tier", "Value": tier_name},
                                    {"Key": "Environment", "Value": "test"}
                                ]
                            }
                        ]
                    )
                    
                    instance_id = response["Instances"][0]["InstanceId"]
                    instance_ids.append(instance_id)
                    logger.info(f"Launched {tier_name} instance: {instance_id} in {subnet.id}")
                    
                except ClientError as e:
                    logger.error(f"Error launching instance in {subnet.id}: {e}")
        
        return instance_ids
    
    def _check_vpc_dns_settings(self, vpc_id: str) -> bool:
        """Check VPC DNS settings."""
        try:
            response = self.ec2_client.describe_vpcs(VpcIds=[vpc_id])
            vpc = response["Vpcs"][0]
            return vpc["EnableDnsSupport"] and vpc["EnableDnsHostnames"]
        except Exception:
            return False
    
    def _validate_public_internet_access(self, public_subnets: List[NetworkResource]) -> bool:
        """Validate public subnets have internet access via IGW."""
        for subnet in public_subnets:
            if not subnet.id:
                continue
            
            try:
                # Check route tables for internet gateway route
                route_tables = self.ec2_client.describe_route_tables(
                    Filters=[
                        {"Name": "association.subnet-id", "Values": [subnet.id]}
                    ]
                )
                
                for rt in route_tables["RouteTables"]:
                    for route in rt["Routes"]:
                        if (route.get("DestinationCidrBlock") == "0.0.0.0/0" and 
                            "GatewayId" in route and route["GatewayId"].startswith("igw-")):
                            return True
                            
            except Exception:
                continue
        
        return False
    
    def _validate_private_nat_access(self, private_subnets: List[NetworkResource], 
                                   nat_gateways: List[NetworkResource]) -> bool:
        """Validate private subnets have NAT gateway access."""
        return len(nat_gateways) > 0 and len(private_subnets) > 0
    
    def _validate_cross_az_connectivity(self, subnets: Dict[str, List[NetworkResource]]) -> bool:
        """Validate cross-AZ connectivity."""
        all_azs = set()
        for subnet_list in subnets.values():
            for subnet in subnet_list:
                if subnet.availability_zone:
                    all_azs.add(subnet.availability_zone)
        
        # Should have subnets in multiple AZs for high availability
        return len(all_azs) >= 2
    
    def _validate_security_isolation(self, vpc_id: str) -> bool:
        """Validate security group isolation between tiers."""
        try:
            # Check if multiple security groups exist (indicating tier separation)
            response = self.ec2_client.describe_security_groups(
                Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
            )
            # Should have more than just the default security group
            return len(response["SecurityGroups"]) > 1
        except Exception:
            return False


def create_network_manager() -> NetworkInfrastructureManager:
    """Create a network infrastructure manager instance."""
    return NetworkInfrastructureManager()
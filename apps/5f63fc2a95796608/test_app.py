import pytest
import time
from typing import Dict, List, Any
from app import NetworkInfrastructureManager, NetworkResource


class TestNetworkInfrastructure:
    """Test suite for network infrastructure management and deployments."""
    
    def test_vpc_infrastructure_exists(self, ec2_client, infrastructure_config):
        """Test that VPC infrastructure components exist after Terraform apply."""
        vpc_name = infrastructure_config["vpc"]["name"]
        
        # Check VPC exists
        vpcs = ec2_client.describe_vpcs(
            Filters=[{"Name": "tag:Name", "Values": [vpc_name]}]
        )
        assert len(vpcs["Vpcs"]) == 1, f"VPC '{vpc_name}' should exist"
        
        vpc = vpcs["Vpcs"][0]
        assert vpc["State"] == "available", "VPC should be in available state"
        assert vpc["CidrBlock"] == infrastructure_config["vpc"]["cidr"]
        
        # Check Internet Gateway exists
        igws = ec2_client.describe_internet_gateways(
            Filters=[{"Name": "attachment.vpc-id", "Values": [vpc["VpcId"]]}]
        )
        assert len(igws["InternetGateways"]) == 1, "Internet Gateway should exist"
        assert igws["InternetGateways"][0]["State"] == "available"
    
    def test_subnet_configuration_validation(self, ec2_client, infrastructure_config):
        """Test that subnets are configured correctly according to specification."""
        vpc_name = infrastructure_config["vpc"]["name"]
        
        # Get VPC ID
        vpcs = ec2_client.describe_vpcs(
            Filters=[{"Name": "tag:Name", "Values": [vpc_name]}]
        )
        vpc_id = vpcs["Vpcs"][0]["VpcId"]
        
        # Get all subnets
        subnets = ec2_client.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )
        
        subnet_count = len(subnets["Subnets"])
        expected_count = (len(infrastructure_config["subnets"]["public"]) + 
                         len(infrastructure_config["subnets"]["private"]))
        assert subnet_count == expected_count, f"Expected {expected_count} subnets, found {subnet_count}"
        
        # Verify subnet properties
        subnet_by_name = {}
        for subnet in subnets["Subnets"]:
            name = next((tag["Value"] for tag in subnet.get("Tags", []) 
                        if tag["Key"] == "Name"), None)
            if name:
                subnet_by_name[name] = subnet
        
        # Check public subnets
        for subnet_key, subnet_config in infrastructure_config["subnets"]["public"].items():
            subnet_name = subnet_config["name"]
            assert subnet_name in subnet_by_name, f"Public subnet '{subnet_name}' should exist"
            
            subnet = subnet_by_name[subnet_name]
            assert subnet["CidrBlock"] == subnet_config["cidr"]
            assert subnet["AvailabilityZone"] == subnet_config["az"]
            assert subnet["MapPublicIpOnLaunch"] is True, "Public subnets should map public IPs"
        
        # Check private subnets
        for subnet_key, subnet_config in infrastructure_config["subnets"]["private"].items():
            subnet_name = subnet_config["name"]
            assert subnet_name in subnet_by_name, f"Private subnet '{subnet_name}' should exist"
            
            subnet = subnet_by_name[subnet_name]
            assert subnet["CidrBlock"] == subnet_config["cidr"]
            assert subnet["AvailabilityZone"] == subnet_config["az"]
    
    def test_infrastructure_discovery_workflow(self, infrastructure_config):
        """Test the complete infrastructure discovery workflow."""
        manager = NetworkInfrastructureManager()
        vpc_name = infrastructure_config["vpc"]["name"]
        
        # Discover infrastructure
        infrastructure = manager.discover_vpc_infrastructure(vpc_name)
        
        # Validate discovery results
        assert infrastructure["vpc"].name == vpc_name
        assert infrastructure["vpc"].cidr == infrastructure_config["vpc"]["cidr"]
        assert infrastructure["vpc"].state == "available"
        
        # Check subnet categorization
        assert len(infrastructure["subnets"]["public"]) > 0, "Should discover public subnets"
        assert len(infrastructure["subnets"]["private"]) > 0, "Should discover private subnets"
        
        # Verify subnet details
        all_subnets = infrastructure["subnets"]["public"] + infrastructure["subnets"]["private"]
        for subnet in all_subnets:
            assert subnet.id is not None
            assert subnet.name is not None
            assert subnet.cidr is not None
            assert subnet.availability_zone is not None
            assert subnet.state == "available"
        
        # Check Internet Gateway
        assert infrastructure["internet_gateway"] is not None
        assert infrastructure["internet_gateway"].id.startswith("igw-")
    
    def test_security_group_creation_and_rules(self, infrastructure_config):
        """Test security group creation with proper tier isolation."""
        manager = NetworkInfrastructureManager()
        vpc_name = infrastructure_config["vpc"]["name"]
        
        # Discover infrastructure to get VPC ID
        infrastructure = manager.discover_vpc_infrastructure(vpc_name)
        vpc_id = infrastructure["vpc"].id
        
        # Create web tier security group
        web_sg_id = manager.create_security_group(
            vpc_id=vpc_id,
            name="test-web-sg",
            description="Test web tier security group",
            ingress_rules=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 80,
                    "ToPort": 80,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 443,
                    "ToPort": 443,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
                }
            ]
        )
        
        assert web_sg_id is not None
        assert web_sg_id.startswith("sg-")
        
        # Verify security group rules
        response = manager.ec2_client.describe_security_groups(GroupIds=[web_sg_id])
        security_group = response["SecurityGroups"][0]
        
        assert len(security_group["IpPermissions"]) == 2
        
        # Check HTTP rule
        http_rule = next((rule for rule in security_group["IpPermissions"] 
                         if rule["FromPort"] == 80), None)
        assert http_rule is not None
        assert http_rule["IpProtocol"] == "tcp"
        assert "0.0.0.0/0" in [ip_range["CidrIp"] for ip_range in http_rule["IpRanges"]]
        
        # Check HTTPS rule
        https_rule = next((rule for rule in security_group["IpPermissions"] 
                          if rule["FromPort"] == 443), None)
        assert https_rule is not None
        assert https_rule["IpProtocol"] == "tcp"
    
    def test_multi_tier_application_deployment(self, infrastructure_config):
        """Test deploying a complete multi-tier application."""
        manager = NetworkInfrastructureManager()
        vpc_name = infrastructure_config["vpc"]["name"]
        
        # Discover infrastructure
        infrastructure = manager.discover_vpc_infrastructure(vpc_name)
        
        # Define application configuration
        app_config = {
            "web": {
                "instances_per_subnet": 1,
                "instance_type": "t3.micro",
                "ami_id": "ami-0c02fb55956c7d316"
            },
            "app": {
                "instances_per_subnet": 1,
                "instance_type": "t3.micro",
                "ami_id": "ami-0c02fb55956c7d316"
            },
            "database": {
                "instances_per_subnet": 1,
                "instance_type": "t3.micro",
                "ami_id": "ami-0c02fb55956c7d316"
            }
        }
        
        # Deploy application
        deployments = manager.deploy_multi_tier_application(infrastructure, app_config)
        
        try:
            # Validate deployment results
            assert "web" in deployments, "Web tier should be deployed"
            assert "app" in deployments, "App tier should be deployed"
            assert "database" in deployments, "Database tier should be deployed"
            
            # Check instance counts
            web_instances = deployments["web"]
            app_instances = deployments["app"]
            db_instances = deployments["database"]
            
            assert len(web_instances) > 0, "Web tier should have instances"
            assert len(app_instances) > 0, "App tier should have instances"
            assert len(db_instances) > 0, "Database tier should have instances"
            
            # Verify instances are running
            all_instance_ids = web_instances + app_instances + db_instances
            
            response = manager.ec2_client.describe_instances(InstanceIds=all_instance_ids)
            running_count = 0
            for reservation in response["Reservations"]:
                for instance in reservation["Instances"]:
                    if instance["State"]["Name"] in ["pending", "running"]:
                        running_count += 1
            
            assert running_count == len(all_instance_ids), "All instances should be pending or running"
            
            # Validate instance placement
            for reservation in response["Reservations"]:
                for instance in reservation["Instances"]:
                    tier_tag = next((tag["Value"] for tag in instance.get("Tags", []) 
                                   if tag["Key"] == "Tier"), None)
                    assert tier_tag in ["web", "app", "database"], "Instance should have valid tier tag"
                    
                    # Web instances should be in public subnets
                    if tier_tag == "web":
                        public_subnet_ids = [s.id for s in infrastructure["subnets"]["public"]]
                        assert instance["SubnetId"] in public_subnet_ids, "Web instances should be in public subnets"
                    
                    # App and DB instances should be in private subnets
                    elif tier_tag in ["app", "database"]:
                        private_subnet_ids = [s.id for s in infrastructure["subnets"]["private"]]
                        assert instance["SubnetId"] in private_subnet_ids, "App/DB instances should be in private subnets"
        
        finally:
            # Clean up instances
            all_instance_ids = []
            for tier_instances in deployments.values():
                all_instance_ids.extend(tier_instances)
            
            if all_instance_ids:
                manager.cleanup_deployment(all_instance_ids)
    
    def test_network_connectivity_validation(self, infrastructure_config):
        """Test comprehensive network connectivity validation."""
        manager = NetworkInfrastructureManager()
        vpc_name = infrastructure_config["vpc"]["name"]
        
        # Discover infrastructure
        infrastructure = manager.discover_vpc_infrastructure(vpc_name)
        
        # Run connectivity validation
        results = manager.validate_network_connectivity(infrastructure)
        
        # Validate test results
        assert isinstance(results, dict), "Results should be a dictionary"
        assert len(results) > 0, "Should have connectivity test results"
        
        # Check specific connectivity tests
        assert "vpc_dns_enabled" in results, "Should test VPC DNS settings"
        assert "public_internet_access" in results, "Should test public internet access"
        assert "cross_az_connectivity" in results, "Should test cross-AZ connectivity"
        
        # VPC should have DNS enabled
        assert results["vpc_dns_enabled"] is True, "VPC should have DNS support enabled"
        
        # Should have cross-AZ connectivity (multiple AZs)
        assert results["cross_az_connectivity"] is True, "Should have subnets in multiple AZs"
        
        # Log results for debugging
        for test_name, test_result in results.items():
            print(f"Connectivity test '{test_name}': {'PASS' if test_result else 'FAIL'}")
    
    def test_high_availability_deployment_pattern(self, infrastructure_config):
        """Test deploying applications across multiple availability zones for high availability."""
        manager = NetworkInfrastructureManager()
        vpc_name = infrastructure_config["vpc"]["name"]
        
        # Discover infrastructure
        infrastructure = manager.discover_vpc_infrastructure(vpc_name)
        
        # Count availability zones
        public_azs = set(subnet.availability_zone for subnet in infrastructure["subnets"]["public"])
        private_azs = set(subnet.availability_zone for subnet in infrastructure["subnets"]["private"])
        
        assert len(public_azs) >= 2, "Should have public subnets in at least 2 AZs for HA"
        assert len(private_azs) >= 2, "Should have private subnets in at least 2 AZs for HA"
        
        # Deploy HA configuration
        app_config = {
            "web": {
                "instances_per_subnet": 1,  # One instance per subnet for HA
                "instance_type": "t3.micro",
                "ami_id": "ami-0c02fb55956c7d316"
            }
        }
        
        deployments = manager.deploy_multi_tier_application(infrastructure, app_config)
        
        try:
            web_instances = deployments["web"]
            
            # Verify instances are distributed across AZs
            response = manager.ec2_client.describe_instances(InstanceIds=web_instances)
            instance_azs = set()
            
            for reservation in response["Reservations"]:
                for instance in reservation["Instances"]:
                    instance_azs.add(instance["Placement"]["AvailabilityZone"])
            
            assert len(instance_azs) >= 2, "Web instances should be distributed across multiple AZs"
            
        finally:
            # Clean up
            all_instance_ids = []
            for tier_instances in deployments.values():
                all_instance_ids.extend(tier_instances)
            
            if all_instance_ids:
                manager.cleanup_deployment(all_instance_ids)
    
    def test_nat_gateway_configuration(self, infrastructure_config):
        """Test NAT Gateway configuration for private subnet internet access."""
        manager = NetworkInfrastructureManager()
        vpc_name = infrastructure_config["vpc"]["name"]
        
        # Discover infrastructure
        infrastructure = manager.discover_vpc_infrastructure(vpc_name)
        
        # Check NAT Gateway presence
        nat_gateways = infrastructure["nat_gateways"]
        
        if len(infrastructure["subnets"]["private"]) > 0:
            # Should have NAT Gateways for private subnet internet access
            # Note: This depends on the Terraform configuration actually creating NAT Gateways
            print(f"Found {len(nat_gateways)} NAT Gateway(s)")
            
            # Verify NAT Gateway placement in public subnets
            if nat_gateways:
                public_subnet_ids = [s.id for s in infrastructure["subnets"]["public"]]
                
                nat_gateway_details = manager.ec2_client.describe_nat_gateways(
                    NatGatewayIds=[ng.id for ng in nat_gateways]
                )
                
                for nat_gw in nat_gateway_details["NatGateways"]:
                    assert nat_gw["SubnetId"] in public_subnet_ids, "NAT Gateway should be in public subnet"
                    assert nat_gw["State"] in ["pending", "available"], "NAT Gateway should be available"
    
    def test_error_handling_and_resilience(self, infrastructure_config):
        """Test error handling and resilience of the network management system."""
        manager = NetworkInfrastructureManager()
        
        # Test 1: Invalid VPC name
        with pytest.raises(ValueError, match="VPC with name .* not found"):
            manager.discover_vpc_infrastructure("nonexistent-vpc")
        
        # Test 2: Duplicate security group creation
        vpc_name = infrastructure_config["vpc"]["name"]
        infrastructure = manager.discover_vpc_infrastructure(vpc_name)
        vpc_id = infrastructure["vpc"].id
        
        # Create security group
        sg_name = "test-duplicate-sg"
        sg_id_1 = manager.create_security_group(
            vpc_id=vpc_id,
            name=sg_name,
            description="Test duplicate security group",
            ingress_rules=[]
        )
        
        # Try to create same security group again (should handle gracefully)
        sg_id_2 = manager.create_security_group(
            vpc_id=vpc_id,
            name=sg_name,
            description="Test duplicate security group",
            ingress_rules=[]
        )
        
        assert sg_id_1 == sg_id_2, "Should return existing security group ID"
        
        # Test 3: Cleanup with empty instance list
        result = manager.cleanup_deployment([])
        assert result is True, "Cleanup should handle empty instance list gracefully"
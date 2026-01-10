import pytest
import time
from unittest.mock import patch, MagicMock
from app import MultiTierApplicationDeployer, DeploymentStrategy, NetworkInfrastructure


class TestMultiTierApplicationDeployer:
    """Test suite for multi-tier application deployment."""
    
    def test_infrastructure_discovery(self, ec2_client):
        """Test discovery of VPC infrastructure created by Terraform."""
        # Create mock VPC
        vpc_response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        
        # Tag the VPC
        ec2_client.create_tags(
            Resources=[vpc_id],
            Tags=[{'Key': 'Name', 'Value': 'test-vpc'}]
        )
        
        # Create public subnet
        public_subnet_response = ec2_client.create_subnet(
            VpcId=vpc_id,
            CidrBlock='10.0.1.0/24',
            AvailabilityZone='us-east-1a'
        )
        public_subnet_id = public_subnet_response['Subnet']['SubnetId']
        
        # Tag public subnet
        ec2_client.create_tags(
            Resources=[public_subnet_id],
            Tags=[
                {'Key': 'Name', 'Value': 'public-web-1'},
                {'Key': 'access_type', 'Value': 'public'}
            ]
        )
        
        # Create private subnet
        private_subnet_response = ec2_client.create_subnet(
            VpcId=vpc_id,
            CidrBlock='10.0.10.0/24',
            AvailabilityZone='us-east-1a'
        )
        private_subnet_id = private_subnet_response['Subnet']['SubnetId']
        
        # Tag private subnet
        ec2_client.create_tags(
            Resources=[private_subnet_id],
            Tags=[
                {'Key': 'Name', 'Value': 'private-app-1'},
                {'Key': 'access_type', 'Value': 'private'}
            ]
        )
        
        # Create Internet Gateway
        igw_response = ec2_client.create_internet_gateway()
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        ec2_client.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        
        # Initialize deployer and discover infrastructure
        deployer = MultiTierApplicationDeployer()
        infrastructure = deployer.discover_infrastructure()
        
        # Assertions
        assert infrastructure.vpc_id == vpc_id
        assert 'public-web-1' in infrastructure.public_subnets
        assert infrastructure.public_subnets['public-web-1'] == public_subnet_id
        assert 'private-app-1' in infrastructure.private_subnets
        assert infrastructure.private_subnets['private-app-1'] == private_subnet_id
        assert infrastructure.internet_gateway_id == igw_id
        assert len(infrastructure.route_tables) > 0
    
    def test_security_group_creation(self, ec2_client):
        """Test creation of security groups for application tiers."""
        # Create VPC first
        vpc_response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        
        infrastructure = NetworkInfrastructure(
            vpc_id=vpc_id,
            public_subnets={'public-1': 'subnet-123'},
            private_subnets={'private-1': 'subnet-456'},
            nat_gateways={},
            internet_gateway_id='igw-123',
            route_tables={}
        )
        
        deployer = MultiTierApplicationDeployer()
        security_groups = deployer.create_security_groups(infrastructure)
        
        # Assertions
        assert 'web-sg' in security_groups
        assert 'app-sg' in security_groups
        assert 'db-sg' in security_groups
        
        # Verify security groups exist
        sg_response = ec2_client.describe_security_groups(
            GroupIds=list(security_groups.values())
        )
        assert len(sg_response['SecurityGroups']) == 3
        
        # Verify security group rules
        for sg in sg_response['SecurityGroups']:
            if sg['GroupName'] == 'web-security-group':
                # Web tier should have HTTP, HTTPS, and SSH access
                ingress_rules = sg['IpPermissions']
                ports = [rule['FromPort'] for rule in ingress_rules if 'FromPort' in rule]
                assert 80 in ports
                assert 443 in ports
                assert 22 in ports
    
    def test_application_tier_deployment(self, ec2_client):
        """Test deployment of a single application tier."""
        # Setup infrastructure
        vpc_response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        
        # Create public subnet for web tier
        public_subnet_response = ec2_client.create_subnet(
            VpcId=vpc_id,
            CidrBlock='10.0.1.0/24',
            AvailabilityZone='us-east-1a'
        )
        public_subnet_id = public_subnet_response['Subnet']['SubnetId']
        
        # Create security group
        sg_response = ec2_client.create_security_group(
            GroupName='web-test-sg',
            Description='Test security group',
            VpcId=vpc_id
        )
        sg_id = sg_response['GroupId']
        
        infrastructure = NetworkInfrastructure(
            vpc_id=vpc_id,
            public_subnets={'public-1': public_subnet_id},
            private_subnets={},
            nat_gateways={},
            internet_gateway_id='igw-123',
            route_tables={}
        )
        
        security_groups = {'web-sg': sg_id}
        
        deployer = MultiTierApplicationDeployer()
        
        # Deploy web tier
        instance_ids = deployer.deploy_application_tier('web', infrastructure, security_groups)
        
        # Assertions
        assert len(instance_ids) == deployer.application_tiers['web'].min_instances
        
        # Verify instances exist
        response = ec2_client.describe_instances(InstanceIds=instance_ids)
        instances = []
        for reservation in response['Reservations']:
            instances.extend(reservation['Instances'])
        
        assert len(instances) == len(instance_ids)
        
        # Verify instance configuration
        for instance in instances:
            assert instance['InstanceType'] == 't3.micro'
            assert instance['SubnetId'] == public_subnet_id
            assert sg_id in [sg['GroupId'] for sg in instance['SecurityGroups']]
            
            # Check tags
            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
            assert 'Name' in tags
            assert tags['Tier'] == 'web'
            assert tags['Environment'] == 'production'
    
    def test_full_application_deployment(self, ec2_client):
        """Test deployment of complete multi-tier application."""
        # Setup comprehensive infrastructure
        vpc_response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        
        # Create multiple subnets
        public_subnet_1 = ec2_client.create_subnet(
            VpcId=vpc_id, CidrBlock='10.0.1.0/24', AvailabilityZone='us-east-1a'
        )['Subnet']['SubnetId']
        
        private_subnet_1 = ec2_client.create_subnet(
            VpcId=vpc_id, CidrBlock='10.0.10.0/24', AvailabilityZone='us-east-1a'
        )['Subnet']['SubnetId']
        
        private_subnet_2 = ec2_client.create_subnet(
            VpcId=vpc_id, CidrBlock='10.0.20.0/24', AvailabilityZone='us-east-1b'
        )['Subnet']['SubnetId']
        
        # Tag subnets appropriately
        ec2_client.create_tags(
            Resources=[public_subnet_1],
            Tags=[
                {'Key': 'Name', 'Value': 'public-web-1'},
                {'Key': 'access_type', 'Value': 'public'}
            ]
        )
        
        ec2_client.create_tags(
            Resources=[private_subnet_1],
            Tags=[
                {'Key': 'Name', 'Value': 'private-app-1'},
                {'Key': 'access_type', 'Value': 'private'}
            ]
        )
        
        ec2_client.create_tags(
            Resources=[private_subnet_2],
            Tags=[
                {'Key': 'Name', 'Value': 'private-app-2'},
                {'Key': 'access_type', 'Value': 'private'}
            ]
        )
        
        # Create Internet Gateway
        igw_response = ec2_client.create_internet_gateway()
        igw_id = igw_response['InternetGateway']['InternetGatewayId']
        ec2_client.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
        
        # Tag VPC
        ec2_client.create_tags(
            Resources=[vpc_id],
            Tags=[{'Key': 'Name', 'Value': 'test-vpc'}]
        )
        
        deployer = MultiTierApplicationDeployer()
        
        # Deploy full application
        deployed_instances = deployer.deploy_full_application(DeploymentStrategy.ROLLING)
        
        # Assertions
        assert 'web' in deployed_instances
        assert 'app' in deployed_instances
        assert 'db' in deployed_instances
        
        # Verify correct number of instances per tier
        assert len(deployed_instances['web']) == deployer.application_tiers['web'].min_instances
        assert len(deployed_instances['app']) == deployer.application_tiers['app'].min_instances
        assert len(deployed_instances['db']) == deployer.application_tiers['db'].min_instances
        
        # Verify instances are distributed across appropriate subnets
        all_instance_ids = []
        for tier_instances in deployed_instances.values():
            all_instance_ids.extend(tier_instances)
        
        response = ec2_client.describe_instances(InstanceIds=all_instance_ids)
        
        web_instances = []
        app_instances = []
        db_instances = []
        
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                tier = tags.get('Tier')
                
                if tier == 'web':
                    web_instances.append(instance)
                elif tier == 'app':
                    app_instances.append(instance)
                elif tier == 'db':
                    db_instances.append(instance)
        
        # Web instances should be in public subnets
        for instance in web_instances:
            assert instance['SubnetId'] == public_subnet_1
        
        # App and DB instances should be in private subnets
        private_subnets = [private_subnet_1, private_subnet_2]
        for instance in app_instances + db_instances:
            assert instance['SubnetId'] in private_subnets
    
    def test_network_connectivity_validation(self, ec2_client):
        """Test validation of network connectivity and routing."""
        # Setup infrastructure with proper routing
        vpc_response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        
        public_subnet = ec2_client.create_subnet(
            VpcId=vpc_id, CidrBlock='10.0.1.0/24', AvailabilityZone='us-east-1a'
        )['Subnet']['SubnetId']
        
        private_subnet = ec2_client.create_subnet(
            VpcId=vpc_id, CidrBlock='10.0.10.0/24', AvailabilityZone='us-east-1a'
        )['Subnet']['SubnetId']
        
        # Create and attach Internet Gateway
        igw = ec2_client.create_internet_gateway()['InternetGateway']['InternetGatewayId']
        ec2_client.attach_internet_gateway(InternetGatewayId=igw, VpcId=vpc_id)
        
        # Create NAT Gateway
        eip = ec2_client.allocate_address(Domain='vpc')['AllocationId']
        nat_gw = ec2_client.create_nat_gateway(
            SubnetId=public_subnet,
            AllocationId=eip
        )['NatGateway']['NatGatewayId']
        
        # Setup route tables
        # Public route table with IGW route
        public_rt = ec2_client.create_route_table(VpcId=vpc_id)['RouteTable']['RouteTableId']
        ec2_client.create_route(
            RouteTableId=public_rt,
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=igw
        )
        ec2_client.associate_route_table(
            RouteTableId=public_rt,
            SubnetId=public_subnet
        )
        
        # Private route table with NAT route  
        private_rt = ec2_client.create_route_table(VpcId=vpc_id)['RouteTable']['RouteTableId']
        ec2_client.create_route(
            RouteTableId=private_rt,
            DestinationCidrBlock='0.0.0.0/0',
            NatGatewayId=nat_gw
        )
        ec2_client.associate_route_table(
            RouteTableId=private_rt,
            SubnetId=private_subnet
        )
        
        # Get route tables for infrastructure
        route_tables_response = ec2_client.describe_route_tables(
            Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}]
        )
        route_tables = {rt['RouteTableId']: rt for rt in route_tables_response['RouteTables']}
        
        infrastructure = NetworkInfrastructure(
            vpc_id=vpc_id,
            public_subnets={'public-1': public_subnet},
            private_subnets={'private-1': private_subnet},
            nat_gateways={nat_gw: public_subnet},
            internet_gateway_id=igw,
            route_tables=route_tables
        )
        
        deployer = MultiTierApplicationDeployer()
        validation_results = deployer.validate_network_connectivity(infrastructure)
        
        # Assertions
        assert validation_results['vpc_exists'] is True
        assert validation_results['public_subnets_exist'] is True
        assert validation_results['private_subnets_exist'] is True
        assert validation_results['nat_gateways_exist'] is True
        assert validation_results['internet_gateway_exists'] is True
        assert validation_results['route_tables_exist'] is True
        assert validation_results['public_internet_routing'] is True
        assert validation_results['private_nat_routing'] is True
        assert validation_results['overall_health'] is True
    
    def test_instance_wait_and_monitoring(self, ec2_client):
        """Test waiting for instances to reach running state."""
        # Create VPC and subnet
        vpc_response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        
        subnet_response = ec2_client.create_subnet(
            VpcId=vpc_id,
            CidrBlock='10.0.1.0/24',
            AvailabilityZone='us-east-1a'
        )
        subnet_id = subnet_response['Subnet']['SubnetId']
        
        # Launch test instances
        response = ec2_client.run_instances(
            ImageId='ami-0abcdef1234567890',
            MinCount=2,
            MaxCount=2,
            InstanceType='t3.micro',
            SubnetId=subnet_id
        )
        
        instance_ids = [instance['InstanceId'] for instance in response['Instances']]
        
        deployer = MultiTierApplicationDeployer()
        
        # Test waiting for instances (should be quick in LocalStack)
        result = deployer.wait_for_instances_running(instance_ids, timeout=30)
        assert result is True
        
        # Verify instances are actually running
        describe_response = ec2_client.describe_instances(InstanceIds=instance_ids)
        for reservation in describe_response['Reservations']:
            for instance in reservation['Instances']:
                assert instance['State']['Name'] in ['running', 'pending']
    
    def test_deployment_strategies(self, ec2_client):
        """Test different deployment strategies."""
        # Setup minimal infrastructure
        vpc_response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        
        public_subnet = ec2_client.create_subnet(
            VpcId=vpc_id, CidrBlock='10.0.1.0/24', AvailabilityZone='us-east-1a'
        )['Subnet']['SubnetId']
        
        private_subnet = ec2_client.create_subnet(
            VpcId=vpc_id, CidrBlock='10.0.10.0/24', AvailabilityZone='us-east-1a'
        )['Subnet']['SubnetId']
        
        # Tag subnets and VPC
        ec2_client.create_tags(
            Resources=[vpc_id],
            Tags=[{'Key': 'Name', 'Value': 'test-vpc'}]
        )
        
        for subnet_id, access_type in [(public_subnet, 'public'), (private_subnet, 'private')]:
            ec2_client.create_tags(
                Resources=[subnet_id],
                Tags=[
                    {'Key': 'Name', 'Value': f'{access_type}-subnet-1'},
                    {'Key': 'access_type', 'Value': access_type}
                ]
            )
        
        deployer = MultiTierApplicationDeployer()
        
        # Test Rolling deployment
        deployed_rolling = deployer.deploy_full_application(DeploymentStrategy.ROLLING)
        assert len(deployed_rolling) == 3  # web, app, db tiers
        
        # Cleanup rolling deployment
        rolling_instances = []
        for tier_instances in deployed_rolling.values():
            rolling_instances.extend(tier_instances)
        deployer.cleanup_application(rolling_instances)
        
        # Test Blue-Green deployment
        deployed_blue_green = deployer.deploy_full_application(DeploymentStrategy.BLUE_GREEN)
        assert len(deployed_blue_green) == 3  # web, app, db tiers
        
        # Verify different deployment behavior (both should create same number of instances)
        for tier in ['web', 'app', 'db']:
            expected_count = deployer.application_tiers[tier].min_instances
            assert len(deployed_blue_green[tier]) == expected_count
    
    def test_cleanup_and_error_handling(self, ec2_client):
        """Test cleanup functionality and error handling scenarios."""
        # Create test instances
        vpc_response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
        vpc_id = vpc_response['Vpc']['VpcId']
        
        subnet_response = ec2_client.create_subnet(
            VpcId=vpc_id,
            CidrBlock='10.0.1.0/24',
            AvailabilityZone='us-east-1a'
        )
        subnet_id = subnet_response['Subnet']['SubnetId']
        
        # Launch instances
        response = ec2_client.run_instances(
            ImageId='ami-0abcdef1234567890',
            MinCount=3,
            MaxCount=3,
            InstanceType='t3.micro',
            SubnetId=subnet_id
        )
        
        instance_ids = [instance['InstanceId'] for instance in response['Instances']]
        
        deployer = MultiTierApplicationDeployer()
        
        # Test successful cleanup
        cleanup_result = deployer.cleanup_application(instance_ids)
        assert cleanup_result is True
        
        # Verify instances are terminated/terminating
        describe_response = ec2_client.describe_instances(InstanceIds=instance_ids)
        for reservation in describe_response['Reservations']:
            for instance in reservation['Instances']:
                assert instance['State']['Name'] in ['terminated', 'terminating', 'shutting-down']
        
        # Test cleanup with empty list
        empty_cleanup = deployer.cleanup_application([])
        assert empty_cleanup is True
        
        # Test error handling for infrastructure discovery with no VPC
        ec2_client.delete_vpc(VpcId=vpc_id)
        
        with pytest.raises(ValueError, match="No VPC found"):
            deployer.discover_infrastructure()
    
    def test_application_tier_configurations(self):
        """Test application tier configurations and user data scripts."""
        deployer = MultiTierApplicationDeployer()
        
        # Test web tier configuration
        web_tier = deployer.application_tiers['web']
        assert web_tier.name == 'web-tier'
        assert web_tier.instance_type == 't3.micro'
        assert web_tier.min_instances == 2
        assert web_tier.subnet_type == 'public'
        assert web_tier.security_group_name == 'web-sg'
        assert 'nginx' in web_tier.user_data_script
        
        # Test app tier configuration
        app_tier = deployer.application_tiers['app']
        assert app_tier.name == 'app-tier'
        assert app_tier.instance_type == 't3.small'
        assert app_tier.min_instances == 2
        assert app_tier.subnet_type == 'private'
        assert app_tier.security_group_name == 'app-sg'
        assert 'docker' in app_tier.user_data_script
        
        # Test db tier configuration
        db_tier = deployer.application_tiers['db']
        assert db_tier.name == 'db-tier'
        assert db_tier.instance_type == 't3.medium'
        assert db_tier.min_instances == 1
        assert db_tier.subnet_type == 'private'
        assert db_tier.security_group_name == 'db-sg'
        assert 'postgresql' in db_tier.user_data_script
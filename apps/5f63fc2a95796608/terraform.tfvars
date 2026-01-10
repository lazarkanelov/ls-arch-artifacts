vpc = {
  name = "test-vpc"
  cidr = "10.0.0.0/16"
}

subnets = {
  public = {
    web-subnet-1a = {
      name = "web-subnet-1a"
      cidr = "10.0.1.0/24"
      az   = "us-east-1a"
      type = "web"
    }
    web-subnet-1b = {
      name = "web-subnet-1b"
      cidr = "10.0.2.0/24"
      az   = "us-east-1b"
      type = "web"
    }
  }
  private = {
    app-subnet-1a = {
      name        = "app-subnet-1a"
      cidr        = "10.0.11.0/24"
      az          = "us-east-1a"
      type        = "app"
      nat_gateway = "NONE"
    }
    app-subnet-1b = {
      name        = "app-subnet-1b"
      cidr        = "10.0.12.0/24"
      az          = "us-east-1b"
      type        = "app"
      nat_gateway = "NONE"
    }
    db-subnet-1a = {
      name        = "db-subnet-1a"
      cidr        = "10.0.21.0/24"
      az          = "us-east-1a"
      type        = "db"
      nat_gateway = "NONE"
    }
    db-subnet-1b = {
      name        = "db-subnet-1b"
      cidr        = "10.0.22.0/24"
      az          = "us-east-1b"
      type        = "db"
      nat_gateway = "NONE"
    }
  }
}

tags_default = {
  Environment = "test"
  Project     = "lsqm-validation"
}

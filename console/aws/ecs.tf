# --- ECS Cluster ---

resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# --- IAM Roles ---

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${var.project_name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow ECS to read secrets
resource "aws_iam_role_policy" "ecs_secrets" {
  name = "${var.project_name}-secrets-access"
  role = aws_iam_role.ecs_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = [
        aws_secretsmanager_secret.app_secrets.arn,
        aws_secretsmanager_secret.db_password.arn,
      ]
    }]
  })
}

resource "aws_iam_role" "ecs_task" {
  name               = "${var.project_name}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# --- CloudWatch Log Groups ---

resource "aws_cloudwatch_log_group" "holly_backend" {
  name              = "/ecs/${var.project_name}/backend"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "holly_agents" {
  name              = "/ecs/${var.project_name}/holly-grace"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "chromadb" {
  name              = "/ecs/${var.project_name}/chromadb"
  retention_in_days = 14
}

# --- Service Discovery (so holly-backend can reach holly-grace by name) ---

resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "${var.project_name}.local"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "holly_agents" {
  name = "holly-grace"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "chromadb" {
  name = "chromadb"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# --- EFS for ChromaDB persistence ---

resource "aws_efs_file_system" "chromadb" {
  tags = { Name = "${var.project_name}-chromadb-efs" }
}

resource "aws_security_group" "efs" {
  name_prefix = "${var.project_name}-efs-"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  tags = { Name = "${var.project_name}-efs-sg" }
}

resource "aws_efs_mount_target" "chromadb" {
  count           = 2
  file_system_id  = aws_efs_file_system.chromadb.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

# --- ECS Task Definition: holly-grace ---

resource "aws_ecs_task_definition" "holly_agents" {
  family                   = "${var.project_name}-holly-grace"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.holly_agents_cpu
  memory                   = var.holly_agents_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "holly-grace"
    image = var.holly_agents_image != "" ? var.holly_agents_image : "${aws_ecr_repository.holly_agents.repository_url}:latest"

    portMappings = [{
      containerPort = 8050
      protocol      = "tcp"
    }]

    environment = [
      { name = "HOST", value = "0.0.0.0" },
      { name = "PORT", value = "8050" },
      { name = "LANGSMITH_PROJECT", value = "holly-grace" },
      { name = "LANGSMITH_TRACING_V2", value = "true" },
      { name = "REDIS_URL", value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0" },
      { name = "CHROMA_URL", value = "http://chromadb.${var.project_name}.local:8000" },
      { name = "OLLAMA_BASE_URL", value = "" },
      { name = "SHOPIFY_SHOP_URL", value = var.shopify_shop_url },
      { name = "SHOPIFY_API_VERSION", value = var.shopify_api_version },
    ]

    secrets = [
      { name = "LANGSMITH_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:LANGSMITH_API_KEY::" },
      { name = "OPENAI_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:OPENAI_API_KEY::" },
      { name = "ANTHROPIC_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:ANTHROPIC_API_KEY::" },
      { name = "SHOPIFY_ACCESS_TOKEN", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:SHOPIFY_ACCESS_TOKEN::" },
      { name = "STRIPE_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:STRIPE_SECRET_KEY::" },
      { name = "PRINTFUL_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:PRINTFUL_API_KEY::" },
      { name = "DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:DATABASE_URL::" },
      { name = "AUTH_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:AUTH_SECRET_KEY::" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.holly_agents.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8050/health')\" || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 120
    }
  }])
}

# --- ECS Task Definition: holly-grace backend ---

resource "aws_ecs_task_definition" "holly_backend" {
  family                   = "${var.project_name}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "holly-backend"
    image = var.holly_backend_image != "" ? var.holly_backend_image : "${aws_ecr_repository.holly_backend.repository_url}:latest"

    portMappings = [{
      containerPort = 8060
      protocol      = "tcp"
    }]

    environment = [
      { name = "HOLLY_AGENTS_URL", value = "http://holly-grace.${var.project_name}.local:8050" },
      { name = "HOLLY_LANGSMITH_PROJECT", value = "holly-grace" },
      { name = "HOLLY_CORS_ORIGINS", value = "[\"*\"]" },
      { name = "HOLLY_CONSOLE_USER_EMAIL", value = "sean.p.allen9@gmail.com" },
    ]

    secrets = [
      { name = "HOLLY_LANGSMITH_API_KEY", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:LANGSMITH_API_KEY::" },
      { name = "HOLLY_CONSOLE_USER_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:CONSOLE_PASSWORD::" },
      { name = "HOLLY_CONSOLE_JWT_SECRET", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:CONSOLE_JWT_SECRET::" },
      { name = "HOLLY_AGENTS_TOKEN", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:HOLLY_AGENTS_TOKEN::" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.holly_backend.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8060/')\" || exit 1"]
      interval    = 30
      timeout     = 10
      retries     = 3
      startPeriod = 30
    }
  }])
}

# --- ECS Task Definition: ChromaDB ---

resource "aws_ecs_task_definition" "chromadb" {
  family                   = "${var.project_name}-chromadb"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  volume {
    name = "chromadb-data"
    efs_volume_configuration {
      file_system_id = aws_efs_file_system.chromadb.id
    }
  }

  container_definitions = jsonencode([{
    name  = "chromadb"
    image = "chromadb/chroma:latest"

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    mountPoints = [{
      sourceVolume  = "chromadb-data"
      containerPath = "/chroma/chroma"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.chromadb.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -sf http://localhost:8000/api/v2/heartbeat || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])
}

# --- ECS Services ---

resource "aws_ecs_service" "holly_agents" {
  name            = "holly-grace"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.holly_agents.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.holly_agents.arn
  }
}

resource "aws_ecs_service" "holly_backend" {
  name            = "holly-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.holly_backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.holly_backend.arn
    container_name   = "holly-backend"
    container_port   = 8060
  }

  depends_on = [aws_lb_listener_rule.api]
}

resource "aws_ecs_service" "chromadb" {
  name            = "chromadb"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.chromadb.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.chromadb.arn
  }

  depends_on = [aws_efs_mount_target.chromadb]
}

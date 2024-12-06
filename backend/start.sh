#!/bin/bash

set -e

# Função para checar se RabbitMQ está rodando
check_rabbit() {
    if rabbitmqctl status > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

echo "Verificando se o RabbitMQ está rodando..."

if ! check_rabbit; then
    echo "RabbitMQ não está rodando. Tentando iniciar..."
    brew services start rabbitmq
    # Aguarda alguns segundos para o RabbitMQ subir
    sleep 5
fi

if check_rabbit; then
    echo "RabbitMQ está rodando. Deletando filas existentes..."
    # Deleta as filas se existirem
    rabbitmqctl delete_queue audio_processing || true
    rabbitmqctl delete_queue audio_processing_retry || true
    rabbitmqctl delete_queue image_processing || true
    rabbitmqctl delete_queue image_processing_retry || true
    rabbitmqctl delete_queue document_processing || true
    rabbitmqctl delete_queue document_processing_retry || true
    rabbitmqctl delete_queue video_processing || true
    rabbitmqctl delete_queue video_processing_retry || true
else
    echo "Não foi possível iniciar o RabbitMQ. As filas não serão deletadas."
fi

echo "Iniciando o servidor..."
uvicorn main:app --reload --port 8001
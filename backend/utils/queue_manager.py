import logging
import json
import os
from aio_pika import connect_robust, Message, DeliveryMode, ExchangeType, IncomingMessage
from aiormq.exceptions import ChannelNotFoundEntity, ChannelPreconditionFailed
import time

logger = logging.getLogger(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")

class QueueManager:
    def __init__(self, amqp_url: str, mcp_server=None):
        self.amqp_url = amqp_url
        self.mcp_server = mcp_server
        self.connection = None
        self.channel = None

    async def initialize(self):
        """Inicializa a conexão com o RabbitMQ"""
        # Garante que os diretórios existem
        os.makedirs(os.path.join(UPLOAD_FOLDER, "processed"), exist_ok=True)
        os.makedirs(os.path.join(UPLOAD_FOLDER, "unprocessed"), exist_ok=True)
        
        await self.connect()
        logger.info("Limpando filas existentes...")
        await self.purge_queues()

    async def connect(self):
        """Estabelece conexão com o RabbitMQ"""
        logger.info("Conectando ao RabbitMQ...")
        self.connection = await connect_robust(self.amqp_url)
        self.channel = await self.connection.channel()

        # Declarando exchange DLX para mensagens mortas
        try:
            # Primeiro tenta declarar sem durable
            await self.channel.declare_exchange(
                'dlx',
                ExchangeType.DIRECT,
                durable=False
            )
            logger.info("Exchange DLX criada")
        except ChannelPreconditionFailed:
            # Se falhar, tenta com durable
            try:
                await self.channel.declare_exchange(
                    'dlx',
                    ExchangeType.DIRECT,
                    durable=True
                )
                logger.info("Exchange DLX criada como durável")
            except Exception as e:
                logger.error(f"Erro ao criar exchange DLX: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Erro ao criar exchange DLX: {str(e)}")
            raise

    async def process_queue(self, queue_name: str, callback):
        """Processa mensagens de uma fila específica"""
        queue = await self.channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                'x-message-ttl': 3600000,  # 1 hora
                'x-dead-letter-exchange': 'dlx',
                'x-dead-letter-routing-key': f"{queue_name}_failed",
                'x-max-priority': 10
            }
        )

        # Declarando fila DLQ correspondente
        dlq = await self.channel.declare_queue(
            f"{queue_name}_failed",
            durable=True
        )

        async def process_message(message: IncomingMessage):
            try:
                data = json.loads(message.body.decode())
                
                # Verifica se a mensagem tem o formato correto
                if 'filename' not in data:
                    logger.error(f"Mensagem inválida na fila {queue_name}: {data}")
                    await message.ack()  # Acknowledge para remover da fila
                    return
                    
                file_path = os.path.join(UPLOAD_FOLDER, data['filename'])
                
                if not os.path.exists(file_path):
                    logger.warning(f"Arquivo não encontrado, ignorando: {file_path}")
                    await message.ack()
                    return

                logger.info(f"Processando arquivo da fila {queue_name}: {data['filename']}")
                await callback(file_path, data)
                await message.ack()
            except json.JSONDecodeError:
                logger.error(f"Erro ao decodificar mensagem JSON da fila {queue_name}")
                await message.ack()  # Acknowledge para remover mensagens mal formatadas
            except Exception as e:
                logger.error(f"Erro processando mensagem da fila {queue_name}: {str(e)}")
                await message.reject(requeue=False)

        await queue.consume(process_message)
        logger.info(f"Consumidor configurado para a fila {queue_name}")

    async def enqueue_task(self, queue_type: str, message: dict):
        """Enfileira uma tarefa"""
        try:
            queue_name = f"{queue_type}_processing"
            
            # Converte a mensagem para JSON
            message_body = json.dumps(message).encode()
            
            # Publica a mensagem
            await self.channel.default_exchange.publish(
                Message(
                    message_body,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type='application/json'
                ),
                routing_key=queue_name
            )
            
            logger.info(f"Tarefa enfileirada na fila {queue_type}: {message}")
            
            # Verifica status da fila após enfileirar
            await self.check_queue_status(queue_name)
            
        except Exception as e:
            logger.error(f"Erro ao enfileirar tarefa: {e}")
            raise

    async def purge_queues(self):
        """Limpa todas as filas"""
        for q in ["audio_processing", "document_processing", "image_processing", "video_processing"]:
            queue = await self.channel.declare_queue(
                q, 
                durable=True,
                arguments={
                    'x-message-ttl': 3600000,
                    'x-dead-letter-exchange': 'dlx',
                    'x-dead-letter-routing-key': f"{q}_failed",
                    'x-max-priority': 10
                }
            )
            await queue.purge()
            logger.info(f"Fila {q} limpa")

            # Também limpa a fila DLQ correspondente
            dlq = await self.channel.declare_queue(
                f"{q}_failed",
                durable=True
            )
            await dlq.purge()
            logger.info(f"Fila {q}_failed limpa")

    async def purge_queue(self, queue_name: str):
        """Limpa uma fila específica"""
        if self.channel:
            queue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    'x-message-ttl': 3600000,
                    'x-dead-letter-exchange': 'dlx',
                    'x-dead-letter-routing-key': f"{queue_name}_failed",
                    'x-max-priority': 10
                }
            )
            await queue.purge()
            logger.info(f"Fila {queue_name} foi limpa")

            # Também limpa a fila DLQ correspondente
            dlq = await self.channel.declare_queue(
                f"{queue_name}_failed",
                durable=True
            )
            await dlq.purge()
            logger.info(f"Fila {queue_name}_failed foi limpa")

    async def close(self):
        """Fecha as conexões"""
        if self.channel:
            await self.channel.close()
        if self.connection:
            await self.connection.close()

    async def setup_consumer(self, queue_name: str, callback):
        """Configura um consumidor para a fila especificada"""
        try:
            queue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                arguments={
                    'x-message-ttl': 3600000,
                    'x-dead-letter-exchange': 'dlx',
                    'x-dead-letter-routing-key': f'{queue_name}_failed',
                    'x-max-priority': 10
                }
            )
            
            logger.info(f"Iniciando consumo da fila {queue_name}")
            
            # Adiciona prefetch_count para controlar quantas mensagens são processadas simultaneamente
            await self.channel.set_qos(prefetch_count=1)
            
            # Configura o consumidor com o callback
            await queue.consume(callback)
            logger.info(f"Consumidor configurado e ativo para a fila {queue_name}")
            
        except Exception as e:
            logger.error(f"Erro ao configurar consumidor para {queue_name}: {e}")
            raise

    async def process_message(self, message: IncomingMessage):
        """Processa uma mensagem da fila"""
        try:
            async with message.process():
                body = json.loads(message.body.decode())
                logger.info(f"Processando mensagem: {body}")
                # Seu código de processamento aqui
                
        except Exception as e:
            logger.error(f"Erro processando mensagem: {e}")
            # Rejeita a mensagem para que vá para a DLQ
            await message.reject(requeue=False)

    async def process_audio_message(self, message: IncomingMessage):
        """Processa mensagem da fila de áudio"""
        try:
            async with message.process():
                body = json.loads(message.body.decode())
                logger.info(f"[AUDIO] Iniciando processamento: {body['file_name']}")
                
                if not self.mcp_server:
                    raise ValueError("MCP Server não inicializado")
                    
                await self.mcp_server.process_audio(
                    file_path=body['file_path'],
                    file_name=body['file_name']
                )
                logger.info(f"[AUDIO] Processamento concluído: {body['file_name']}")
                
        except Exception as e:
            logger.error(f"[AUDIO] Erro no processamento: {e}")
            await message.reject(requeue=False)

    async def process_document_message(self, message: IncomingMessage):
        """Processa mensagem da fila de documento"""
        try:
            async with message.process():
                body = json.loads(message.body.decode())
                logger.info(f"Processando mensagem de documento: {body}")
                
                if not self.mcp_server:
                    raise ValueError("MCP Server não inicializado")
                    
                await self.mcp_server.process_document(
                    file_path=body['file_path'],
                    file_name=body['file_name']
                )
                
        except Exception as e:
            logger.error(f"Erro processando documento: {e}")
            await message.reject(requeue=False)

    async def process_image_message(self, message: IncomingMessage):
        """Processa mensagem da fila de imagem"""
        try:
            async with message.process():
                body = json.loads(message.body.decode())
                logger.info(f"Processando mensagem de imagem: {body}")
                
                if not self.mcp_server:
                    raise ValueError("MCP Server não inicializado")
                    
                await self.mcp_server.process_image(
                    file_path=body['file_path'],
                    file_name=body['file_name']
                )
                
        except Exception as e:
            logger.error(f"Erro processando imagem: {e}")
            await message.reject(requeue=False)

    async def process_video_message(self, message: IncomingMessage):
        """Processa mensagem da fila de vídeo"""
        try:
            async with message.process():
                body = json.loads(message.body.decode())
                logger.info(f"Processando mensagem de vídeo: {body}")
                
                if not self.mcp_server:
                    raise ValueError("MCP Server não inicializado")
                    
                await self.mcp_server.process_video(
                    file_path=body['file_path'],
                    file_name=body['file_name']
                )
                
        except Exception as e:
            logger.error(f"Erro processando vídeo: {e}")
            await message.reject(requeue=False)

    async def check_queue_status(self, queue_name: str):
        """Verifica o status de uma fila"""
        try:
            queue = await self.channel.declare_queue(
                queue_name,
                durable=True,
                passive=True  # Não cria a fila, apenas verifica
            )
            message_count = queue.declaration_result.message_count
            consumer_count = queue.declaration_result.consumer_count
            logger.info(f"Fila {queue_name}: {message_count} mensagens, {consumer_count} consumidores")
            return message_count, consumer_count
        except Exception as e:
            logger.error(f"Erro verificando status da fila {queue_name}: {e}")
            return 0, 0
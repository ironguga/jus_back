import logging
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

logger = logging.getLogger(__name__)

class Summarizer:
    """
    Classe responsável pela sumarização de texto usando um modelo pré-treinado, por padrão o 'facebook/bart-large-cnn'.

    Funcionalidades:
    - Carregamento do modelo e tokenizer no construtor.
    - Método `summarize` que recebe texto bruto e retorna um sumário.
    - Opções para ajustar o comprimento máximo e mínimo do sumário.
    - Checagem caso o texto seja muito curto, evitando sumarização desnecessária.
    """

    def __init__(self, model_name: str = "facebook/bart-large-cnn"):
        """
        Construtor do Summarizer.

        :param model_name: Nome do modelo a ser carregado do HuggingFace Hub. Padrão: "facebook/bart-large-cnn".
        """
        logger.info("Carregando modelo de sumarização local...")

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
            logger.info(f"Modelo de sumarização '{model_name}' carregado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao carregar o modelo de sumarização '{model_name}': {e}")
            raise

    def summarize(
        self,
        text: str,
        max_length: int = 100,
        min_length: int = 30,
        length_penalty: float = 2.0,
        num_beams: int = 4,
        early_stopping: bool = True
    ) -> str:
        """
        Gera um sumário do texto fornecido usando o modelo.

        :param text: Texto a ser resumido.
        :param max_length: Comprimento máximo do sumário gerado (em tokens). Padrão: 100.
        :param min_length: Comprimento mínimo do sumário gerado (em tokens). Padrão: 30.
        :param length_penalty: Controla a penalidade de comprimento. 
                               >1.0 encoraja sumários mais curtos, <1.0 sumários mais longos. Padrão: 2.0.
        :param num_beams: Número de feixes (beams) usados na busca do melhor sumário. Padrão: 4.
        :param early_stopping: Se True, a geração para assim que encontrar uma boa hipótese. Padrão: True.

        :return: Uma string contendo o sumário do texto.
        """

        # Verifica se o texto é muito curto e não justifica um sumário
        if len(text.strip()) == 0:
            logger.debug("Texto vazio recebido. Retornando string vazia.")
            return ""

        if len(text) < 200:
            logger.debug("Texto curto (menos de 200 caracteres), sumarização não é necessária. Retornando texto original.")
            return text

        # Logando algumas informações
        logger.debug(
            f"Sumarizando texto com {len(text)} caracteres. "
            f"Parâmetros: max_length={max_length}, min_length={min_length}, "
            f"length_penalty={length_penalty}, num_beams={num_beams}, early_stopping={early_stopping}"
        )

        # Tokenização com truncamento se ultrapassar 512 tokens
        # Isso evita erros ao tentar sumariar textos muito longos
        try:
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512
            )
        except Exception as e:
            logger.error(f"Erro ao tokenizar o texto para sumarização: {e}")
            return text  # Retorna o texto original em caso de falha

        # Geração do sumário
        try:
            summary_ids = self.model.generate(
                inputs["input_ids"],
                max_length=max_length,
                min_length=min_length,
                length_penalty=length_penalty,
                num_beams=num_beams,
                early_stopping=early_stopping
            )
        except Exception as e:
            logger.error(f"Erro ao gerar sumário com o modelo: {e}")
            return text  # Em caso de falha na geração, retorna o texto original

        # Decodifica o sumário gerado
        summary = self.tokenizer.decode(summary_ids[0], skip_special_tokens=True)
        logger.debug(f"Sumarização concluída. Tamanho do sumário: {len(summary)} caracteres.")

        # Verifica se o sumário está vazio ou muito curto (pode acontecer se o modelo não conseguir sumarizar adequadamente)
        if len(summary.strip()) == 0:
            logger.warning("Sumário gerado está vazio. Retornando texto original.")
            return text

        return summary
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import logging

logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self, model_name="facebook/bart-large-cnn"):
        logger.info("Carregando modelo de sumarização local...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        logger.info("Modelo de sumarização carregado.")

    def summarize(self, text, max_length=100):
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        summary_ids = self.model.generate(
            inputs["input_ids"],
            max_length=max_length,
            min_length=30,
            length_penalty=2.0,
            num_beams=4,
            early_stopping=True
        )
        return self.tokenizer.decode(summary_ids[0], skip_special_tokens=True)
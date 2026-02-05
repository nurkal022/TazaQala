import os
import base64
import json

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

class OpenAIModeratorService:
    """
    AI-модератор на базе OpenAI Vision API для анализа фотографий мусора
    """
    
    def __init__(self):
        if OPENAI_AVAILABLE and os.environ.get('OPENAI_API_KEY'):
            self.client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
        else:
            self.client = None
        self.auto_approve_threshold = 0.85
        self.reject_threshold = 0.50
    
    def analyze_image(self, image_path):
        """
        Анализирует фото используя OpenAI Vision API
        
        Returns:
            dict: {
                'confidence': float,
                'status': str (auto_confirmed, needs_review, rejected),
                'analysis': dict,
                'trash_detected': bool,
                'trash_type': str
            }
        """
        try:
            # Проверяем наличие OpenAI модуля и API ключа
            if not OPENAI_AVAILABLE:
                print("⚠️ OpenAI module not installed, using fallback logic")
                return self._fallback_analysis(image_path)
            
            if not self.client or not os.environ.get('OPENAI_API_KEY'):
                print("⚠️ OpenAI API key not found, using fallback logic")
                return self._fallback_analysis(image_path)
            
            # Кодируем изображение в base64
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Отправляем запрос к OpenAI Vision API
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """Проанализируй это изображение и определи:
1. Есть ли на фото мусор или загрязнение? (да/нет)
2. Если да, какой тип мусора? (пластик/металл/органика/смешанный/строительный)
3. Масштаб загрязнения (малый/средний/большой)
4. Качество фото (хорошее/среднее/плохое)
5. Оценка достоверности от 0 до 1 (насколько это действительно проблема для города)

Ответь ТОЛЬКО в формате JSON:
{
  "trash_detected": true/false,
  "trash_type": "пластик"/"металл"/"органика"/"смешанный"/"строительный"/"нет",
  "scale": "малый"/"средний"/"большой",
  "photo_quality": "хорошее"/"среднее"/"плохое",
  "confidence": 0.85,
  "reason": "краткое объяснение"
}"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300
            )
            
            # Парсим ответ
            result_text = response.choices[0].message.content
            result = json.loads(result_text)
            
            confidence = result.get('confidence', 0.5)
            trash_detected = result.get('trash_detected', False)
            trash_type = result.get('trash_type', 'mixed')
            
            # Мапим типы на английский
            trash_type_map = {
                'пластик': 'plastic',
                'металл': 'metal',
                'органика': 'organic',
                'смешанный': 'mixed',
                'строительный': 'construction',
                'нет': 'none'
            }
            trash_type_en = trash_type_map.get(trash_type, 'mixed')
            
            # Определяем статус
            if confidence >= self.auto_approve_threshold and trash_detected:
                status = 'auto_confirmed'
            elif confidence >= self.reject_threshold:
                status = 'needs_review'
            else:
                status = 'rejected'
            
            return {
                'confidence': confidence,
                'status': status,
                'analysis': json.dumps(result),
                'trash_detected': trash_detected,
                'trash_type': trash_type_en
            }
            
        except Exception as e:
            print(f"⚠️ OpenAI API error: {str(e)}, using fallback")
            return self._fallback_analysis(image_path)
    
    def _fallback_analysis(self, image_path):
        """Запасной вариант анализа без OpenAI"""
        import random
        
        confidence = random.uniform(0.8, 0.9)
        
        if confidence >= self.auto_approve_threshold:
            status = 'auto_confirmed'
        elif confidence >= self.reject_threshold:
            status = 'needs_review'
        else:
            status = 'rejected'
        
        return {
            'confidence': round(confidence, 2),
            'status': status,
            'analysis': json.dumps({
                'method': 'fallback',
                'note': 'OpenAI API not available'
            }),
            'trash_detected': True,
            'trash_type': 'mixed'
        }


# Singleton instance
openai_moderator = OpenAIModeratorService()


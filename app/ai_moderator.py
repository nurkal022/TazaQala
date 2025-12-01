import cv2
import numpy as np
from PIL import Image
import json
import os

class AIModeratorService:
    """
    AI-модератор для анализа фотографий мусора
    В production версии здесь будет интеграция с ML моделью (YOLOv8, ResNet и т.д.)
    Для MVP используется упрощенная логика на базе компьютерного зрения
    """
    
    def __init__(self):
        self.min_confidence = 0.0
        self.auto_approve_threshold = 0.85
        self.reject_threshold = 0.50
    
    def analyze_image(self, image_path):
        """
        Анализирует фото и возвращает результат модерации
        
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
            # Загружаем изображение
            image = cv2.imread(image_path)
            if image is None:
                return self._create_response(0.0, 'rejected', 'Невозможно прочитать изображение')
            
            # Проверка качества изображения
            quality_score = self._check_image_quality(image)
            
            # Проверка на наличие мусора (упрощенная логика для MVP)
            trash_score = self._detect_trash(image)
            
            # Проверка на дубликаты (хеш изображения)
            image_hash = self._calculate_image_hash(image)
            
            # Определение типа мусора
            trash_type = self._classify_trash_type(image)
            
            # Итоговая оценка достоверности
            confidence = self._calculate_final_confidence(quality_score, trash_score)
            
            # Определение статуса
            if confidence >= self.auto_approve_threshold:
                status = 'auto_confirmed'
            elif confidence >= self.reject_threshold:
                status = 'needs_review'
            else:
                status = 'rejected'
            
            analysis = {
                'quality_score': round(quality_score, 2),
                'trash_score': round(trash_score, 2),
                'image_hash': image_hash,
                'trash_type': trash_type,
                'image_size': image.shape,
                'model_version': 'mvp_v1.0'
            }
            
            return {
                'confidence': round(confidence, 2),
                'status': status,
                'analysis': json.dumps(analysis),
                'trash_detected': trash_score > 0.5,
                'trash_type': trash_type
            }
            
        except Exception as e:
            print(f"Error in AI analysis: {str(e)}")
            return self._create_response(0.0, 'needs_review', f'Ошибка анализа: {str(e)}')
    
    def _check_image_quality(self, image):
        """Проверяет качество изображения (резкость, яркость)"""
        # Проверка резкости через Laplacian
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Проверка яркости
        brightness = np.mean(gray)
        
        # Оценка качества (0-1)
        sharpness_score = min(laplacian_var / 500, 1.0)
        brightness_score = 1.0 - abs(brightness - 127) / 127
        
        return (sharpness_score * 0.6 + brightness_score * 0.4)
    
    def _detect_trash(self, image):
        """
        Упрощенное обнаружение мусора для MVP
        В production: YOLOv8 или custom CNN модель
        """
        # Конвертируем в HSV для анализа цветов
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Детекция пластика (яркие цвета)
        lower_plastic = np.array([0, 50, 50])
        upper_plastic = np.array([180, 255, 255])
        plastic_mask = cv2.inRange(hsv, lower_plastic, upper_plastic)
        
        # Детекция металла/стекла (блики)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        
        # Детекция органики (коричневые/темные оттенки)
        lower_organic = np.array([10, 50, 20])
        upper_organic = np.array([30, 255, 200])
        organic_mask = cv2.inRange(hsv, lower_organic, upper_organic)
        
        # Подсчет пикселей
        total_pixels = image.shape[0] * image.shape[1]
        trash_pixels = cv2.countNonZero(plastic_mask) + cv2.countNonZero(bright_mask) + cv2.countNonZero(organic_mask)
        
        # Процент "мусорных" пикселей
        trash_ratio = trash_pixels / total_pixels
        
        # Эвристика: если больше 15% изображения - потенциальный мусор
        base_score = min(trash_ratio * 5, 1.0)
        
        # Для MVP добавляем случайную вариацию для реалистичности
        # В production это будет результат ML модели
        return min(base_score + np.random.uniform(0.1, 0.3), 1.0)
    
    def _calculate_image_hash(self, image):
        """Вычисляет перцептивный хеш для обнаружения дубликатов"""
        # Уменьшаем изображение
        small = cv2.resize(image, (8, 8), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        
        # Вычисляем среднее
        avg = gray.mean()
        
        # Создаем хеш
        hash_str = ''.join(['1' if pixel > avg else '0' for pixel in gray.flatten()])
        return hex(int(hash_str, 2))[2:]
    
    def _classify_trash_type(self, image):
        """Классифицирует тип мусора"""
        # Упрощенная логика для MVP
        # В production: multi-label classification model
        
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Пластик (яркие насыщенные цвета)
        plastic_mask = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([180, 255, 255]))
        plastic_ratio = cv2.countNonZero(plastic_mask) / (image.shape[0] * image.shape[1])
        
        # Металл/стекло (блестящие поверхности)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, metal_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        metal_ratio = cv2.countNonZero(metal_mask) / (image.shape[0] * image.shape[1])
        
        # Органика (темные/коричневые оттенки)
        organic_mask = cv2.inRange(hsv, np.array([10, 30, 30]), np.array([30, 255, 150]))
        organic_ratio = cv2.countNonZero(organic_mask) / (image.shape[0] * image.shape[1])
        
        # Определяем преобладающий тип
        ratios = {
            'plastic': plastic_ratio,
            'metal': metal_ratio,
            'organic': organic_ratio
        }
        
        trash_type = max(ratios, key=ratios.get)
        
        # Если все значения низкие - общий мусор
        if max(ratios.values()) < 0.1:
            return 'mixed'
        
        return trash_type
    
    def _calculate_final_confidence(self, quality_score, trash_score):
        """Вычисляет итоговую оценку достоверности"""
        # Взвешенная сумма
        confidence = (quality_score * 0.3 + trash_score * 0.7)
        return confidence
    
    def _create_response(self, confidence, status, message):
        """Создает стандартный ответ"""
        return {
            'confidence': round(confidence, 2),
            'status': status,
            'analysis': json.dumps({'message': message}),
            'trash_detected': False,
            'trash_type': 'unknown'
        }
    
    def is_duplicate(self, image_hash, existing_hashes, threshold=5):
        """
        Проверяет, является ли изображение дубликатом
        threshold: максимальное расстояние Хэмминга для считания дубликатом
        """
        for existing_hash in existing_hashes:
            distance = self._hamming_distance(image_hash, existing_hash)
            if distance <= threshold:
                return True
        return False
    
    def _hamming_distance(self, hash1, hash2):
        """Вычисляет расстояние Хэмминга между двумя хешами"""
        try:
            return bin(int(hash1, 16) ^ int(hash2, 16)).count('1')
        except:
            return 100  # Если ошибка - считаем что не дубликат


# Singleton instance
ai_moderator = AIModeratorService()


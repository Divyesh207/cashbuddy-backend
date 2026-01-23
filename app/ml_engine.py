import os
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class FinanceAI:
    @staticmethod
    def parse_sms(sms_text: str):
        api_key = os.getenv("GEMINI_API_KEY")
        
        # 1. Try AI parsing if Key exists
        if api_key:
            try:
                genai.configure(api_key=api_key)
                # Using 1.5 Flash as it is efficient for extraction tasks
                model = genai.GenerativeModel('gemini-1.5-flash') 
                
                prompt = f"""
                You are a financial transaction parser. Analyze this SMS text: "{sms_text}"
                
                Extract the following fields and return ONLY a raw JSON object (no markdown formatting):
                - description: A short summary of the transaction.
                - amount: The numeric value (float).
                - type: "Income" if money was credited/received, "Expense" if debited/spent.
                - category: Choose exactly one from [Food, Travel, Shopping, Utilities, Housing, Health, Education, Entertainment, Other].
                
                If the text is not a transaction, return amount 0.
                """
                
                response = model.generate_content(prompt)
                
                # Clean potential markdown code blocks
                clean_text = response.text.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                
                return json.loads(clean_text)
            except Exception as e:
                print(f"AI Parse Error: {e}")
        
        # 2. Fallback Regex Parsing (if no API key or API fails)
        # Matches patterns like "Rs. 500", "INR 500", "500.00 debited"
        amount_match = re.search(r'(?i)(rs\.?|inr)\s*([\d,]+(\.\d{2})?)', sms_text)
        if not amount_match:
             amount_match = re.search(r'([\d,]+(\.\d{2})?)\s*(debited|credited)', sms_text)

        amount = 0.0
        if amount_match:
            # Handle group selection carefully based on regex used
            val_str = amount_match.group(2) if 'rs' in amount_match.group(0).lower() or 'inr' in amount_match.group(0).lower() else amount_match.group(1)
            try:
                amount = float(val_str.replace(',', ''))
            except:
                amount = 0.0
            
        is_credit = bool(re.search(r'(?i)(credited|received|deposited|added)', sms_text))
        
        return {
            "description": "Extracted from SMS",
            "amount": amount,
            "type": "Income" if is_credit else "Expense",
            "category": "Other"
        }

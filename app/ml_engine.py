import os
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

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
        
        # 1. Try local "Training" (Keyword Matching) FIRST
        # This acts as a local cache/rule engine for common merchants
        keyword_map = {
            "zomato": {"category": "Food", "type": "Expense"},
            "swiggy": {"category": "Food", "type": "Expense"},
            "uber": {"category": "Travel", "type": "Expense"},
            "ola": {"category": "Travel", "type": "Expense"},
            "rapido": {"category": "Travel", "type": "Expense"},
            "blinkit": {"category": "Shopping", "type": "Expense"},
            "zepto": {"category": "Shopping", "type": "Expense"},
            "amazon": {"category": "Shopping", "type": "Expense"},
            "flipkart": {"category": "Shopping", "type": "Expense"},
            "netflix": {"category": "Entertainment", "type": "Expense"},
            "spotify": {"category": "Entertainment", "type": "Expense"},
            "jiomart": {"category": "Shopping", "type": "Expense"},
            "d-mart": {"category": "Shopping", "type": "Expense"},
            "starbucks": {"category": "Food", "type": "Expense"},
            "mcdonalds": {"category": "Food", "type": "Expense"},
            "kfc": {"category": "Food", "type": "Expense"},
            "bookmyshow": {"category": "Entertainment", "type": "Expense"},
            "salary": {"category": "Salary", "type": "Income"},
            "interest": {"category": "Savings", "type": "Income"},
            "refund": {"category": "Other", "type": "Income"},
        }
        
        lower_text = sms_text.lower()
        matched_data = {}
        
        for key, data in keyword_map.items():
            if key in lower_text:
                matched_data = data
                matched_data['description'] = f"Payment to {key.capitalize()}" if data['type'] == 'Expense' else f"{key.capitalize()} Received"
                break
        
        # 2. Extract Amount using Regex (Universal)
        # Prioritize finding amount associated with Debit/Credit keywords to avoid "Avl Bal"
        amount = 0.0
        # Look for "Rs. 140" preceded by Debit/Spent/Paid variants (capture group 2 is amount)
        # matches: "Debit Rs.140.00", "Paid Rs 500", "Sent Rs. 1000"
        strategic_amount = re.search(r'(?:debit|spent|paid|sent|to|credited|received)\s*(?:rs\.?|inr|₹)?\s*([\d,]+(?:\.\d{1,2})?)', lower_text)
        
        if strategic_amount:
             try:
                amount = float(strategic_amount.group(1).replace(',', ''))
             except: pass
        
        if amount == 0.0:
            # Fallback to just finding the first currency occurrence
            amount_match = re.search(r'(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)', lower_text)
            if amount_match:
                try:
                    amount = float(amount_match.group(1).replace(',', ''))
                except: pass

        # 3. Extract Description (Payee)
        # Try to find "UPI to <Name>" or "Paid to <Name>"
        description = "Extracted Transaction"
        payee_match = re.search(r'(?:upi to|paid to|transfer to|sent to)\s+([a-zA-Z0-9\s]+?)(?=\s+(?:on|via|ref|bal|avl|from)|$|\.)', lower_text)
        if payee_match:
            payee = payee_match.group(1).strip().title()
            description = f"Paid to {payee}"
            # Auto-categorize known generic terms if not already mapped
            if not matched_data:
                if "food" in payee.lower(): matched_data = {"category": "Food", "type": "Expense"}
                elif "mart" in payee.lower() or "store" in payee.lower(): matched_data = {"category": "Shopping", "type": "Expense"}

        elif matched_data:
             description = matched_data['description'] # Use keyword map description if no specific payee found

        # 4. Extract Date
        import datetime
        date_str = datetime.date.today().isoformat() # Default to today
        # Matches: 10-02-26, 10/02/2026, 2026-02-10
        date_match = re.search(r'(\d{2}[-/]\d{2}[-/]\d{2,4})', sms_text)
        if date_match:
            try:
                d_str = date_match.group(1).replace('/', '-')
                # Handle 2-digit year
                parts = d_str.split('-')
                if len(parts[2]) == 2: parts[2] = '20' + parts[2]
                parsed_date = datetime.datetime.strptime(f"{parts[2]}-{parts[1]}-{parts[0]}", "%Y-%m-%d").date()
                date_str = parsed_date.isoformat()
            except: pass

        # If we found a keyword match and amount, return immediately (Local "AI")
        # Update matched_data with extracted amount/date if valid
        if matched_data and amount > 0:
            return {
                "description": description,
                "amount": amount,
                "type": matched_data.get('type', 'Expense'),
                "category": matched_data.get('category', 'Other')
            }

        # 5. If local match failed, try Gemini API (if key exists)
        if api_key:
            try:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash') 
                
                prompt = f"""
                You are a parser. Analyze: "{sms_text}"
                Return strictly JSON:
                {{
                    "description": "{description if description != 'Extracted Transaction' else 'Short summary'}",
                    "amount": {amount if amount > 0 else 0.0},
                    "type": "Income" or "Expense",
                    "category": "One of [Food, Travel, Shopping, Utilities, Housing, Health, Education, Entertainment, Salary, Other]",
                    "date": "{date_str}" (YYYY-MM-DD)
                }}
                """
                
                response = model.generate_content(prompt)
                clean_text = response.text.strip().replace('```json', '').replace('```', '')
                return json.loads(clean_text)
            except Exception as e:
                print(f"AI Parse Error: {e}")
        
        # 6. Fallback if everything fails
        is_credit = bool(re.search(r'(credit|receiv|deposit|add)', lower_text))
        return {
            "description": description,
            "amount": amount,
            "type": "Income" if is_credit else "Expense",
            "category": "Other"
        }

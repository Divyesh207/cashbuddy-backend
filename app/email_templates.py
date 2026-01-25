def get_otp_email_html(otp_code: str, user_name: str = "User") -> str:
    """
    Returns a professional HTML email template for OTP verification.
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CashBuddy Verification Code</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f8fafc;
                margin: 0;
                padding: 0;
                line-height: 1.6;
                color: #334155;
            }}
            .container {{
                max-width: 500px;
                margin: 40px auto;
                background-color: #ffffff;
                border-radius: 16px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                overflow: hidden;
            }}
            .header {{
                background-color: #059669; /* Emerald 600 */
                padding: 32px 20px;
                text-align: center;
            }}
            .logo-text {{
                color: #ffffff;
                font-size: 24px;
                font-weight: bold;
                margin: 0;
            }}
            .content {{
                padding: 40px 30px;
                text-align: center;
            }}
            .greeting {{
                font-size: 18px;
                margin-bottom: 20px;
                color: #1e293b;
            }}
            .otp-box {{
                background-color: #f0fdf4;
                border: 2px dashed #059669;
                border-radius: 12px;
                padding: 20px;
                margin: 30px 0;
                display: inline-block;
            }}
            .otp-code {{
                font-family: 'Courier New', Courier, monospace;
                font-size: 32px;
                font-weight: bold;
                color: #047857;
                letter-spacing: 8px;
                margin: 0;
            }}
            .footer {{
                background-color: #f1f5f9;
                padding: 20px;
                text-align: center;
                font-size: 12px;
                color: #64748b;
            }}
            .warning {{
                font-size: 13px;
                color: #64748b;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 class="logo-text">CashBuddy 💸</h1>
            </div>
            <div class="content">
                <p class="greeting">Hello, <strong>{user_name}</strong>!</p>
                <p>To secure your account, please enter the following verification code:</p>
                
                <div class="otp-box">
                    <p class="otp-code">{otp_code}</p>
                </div>
                
                <p class="warning">This code will expire in 10 minutes.<br>If you did not request this code, please ignore this email.</p>
            </div>
            <div class="footer">
                &copy; 2026 CashBuddy Finance Manager. All rights reserved.
            </div>
        </div>
    </body>
    </html>
    """

import customtkinter as ctk
from database import initialize_database
from ui.login_window import LoginWindow


def main():
    initialize_database()

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    app = ctk.CTk()
    app.withdraw()  # Hide root window

    login = LoginWindow(app)
    login.mainloop()


if __name__ == "__main__":
    main()
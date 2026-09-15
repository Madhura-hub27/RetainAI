# RetainIQ - Employee Feedback & Intelligence System

RetainIQ is an enterprise-grade HR intelligence platform designed to monitor, analyze, and manage employee feedback and sentiment in real-time. Built with a high-performance backend and a secure cloud-native database architecture, it empowers organizations to improve employee retention through data-driven insights.

## 🚀 Live Demo
Experience the live application here:
[RetainIQ Live Application](https://pulseai-2.onrender.com)

---

## 🛠️ Tech Stack & Architecture

* **Backend Framework:** FastAPI (Python) - Chosen for high concurrency, automatic data validation, and blazing-fast performance.
* **Database Management:** MongoDB Atlas (Cloud NoSQL Database) - Provides scalable, flexible, and secure document storage for user credentials and feedback metrics.
* **Frontend UI:** HTML5, CSS3, Modern JavaScript - Designed with a responsive, sleek dark-themed analytics layout.
* **Cloud Hosting & Deployment:** Render - Continuous deployment pipeline connected for seamless production releases.

---

## 📋 Key Features & Capabilities

* **Secure Authentication System:** Role-based login and registration system safeguarding sensitive HR metrics.
* **Employee Feedback Processing:** Structured ingestion pipeline for handling dynamic employee reviews and text-based feedback.
* **Sentiment Analysis Engine:** Evaluates employee sentiment scores to flag potential disengagement risks early.
* **Cloud Persistence:** Fully migrated from local volatile storage to a globally accessible, highly available MongoDB Atlas cluster.
* **Responsive Analytics UI:** Clean dashboard interface providing immediate visual feedback for human resource operations.

---

## ⚙️ Project Structure

```text
RetainIQ/
│
├── static/             # Frontend assets (HTML, CSS, JS files)
├── main.py             # FastAPI core application & route handlers
├── requirements.txt    # Python dependencies and package versions
└── Dockerfile          # Container configuration for cloud deployment

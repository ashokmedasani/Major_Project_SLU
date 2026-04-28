document.addEventListener("DOMContentLoaded", function () {
    const botBtn = document.getElementById("carebotBtn");
    const botBox = document.getElementById("carebotBox");
    const closeBtn = document.getElementById("carebotClose");
    const messages = document.getElementById("carebotMessages");
    const input = document.getElementById("carebotInput");
    const sendBtn = document.getElementById("carebotSend");
    const faqButtons = document.querySelectorAll(".carebot-faq-btn");

    let started = false;
    let isTyping = false;

    const linkedinURL = "https://www.linkedin.com/in/ashok-medasani/";

    const answers = {
        "what is carefinder": "CareFinder is a healthcare decision-support prototype built for diabetes hospital selection. It helps users explore hospitals, compare cost and coverage, and understand predicted healthcare trends using synthetic Synthea data.",
        "how to start": "Please select your state first. After selecting a state, go to Recommendations to see top hospitals based on visits, coverage, and recommendation score.",
        "recommendations": "The Recommendations page shows top hospitals for the selected state and filters. You can view hospital details or select multiple hospitals to compare.",
        "compare": "The Compare page allows you to compare 2 to 4 hospitals side by side using visits, cost, coverage, out-of-pocket values, and predictive charts.",
        "hospital detail": "The Hospital Detail page shows one hospital’s location, cost summary, insurance coverage, out-of-pocket amount, historical trends, and future predictions.",
        "data source": "CareFinder uses synthetic healthcare data generated using Synthea. This is not real patient data.",
        "prediction": "CareFinder uses trained machine learning models saved as PKL files. These models help forecast future visits, patients, hospitals, cost, coverage, and out-of-pocket values.",
        "insurance": "Insurance payer filter helps users understand hospital performance based on selected payer names and related coverage values.",
        "contact": "If the chatbot does not answer your question, please contact Ashok Medasani on LinkedIn:"
    };

    function scrollBottom() {
        messages.scrollTop = messages.scrollHeight;
    }

    function addUserMessage(text) {
        const div = document.createElement("div");
        div.className = "carebot-msg user";
        div.innerText = text;
        messages.appendChild(div);
        scrollBottom();
    }

    function addBotTypingMessage(text) {
        if (isTyping) return;
        isTyping = true;

        const div = document.createElement("div");
        div.className = "carebot-msg bot";
        messages.appendChild(div);

        // Detect LinkedIn
        const needsLink =
            text.includes("LinkedIn") ||
            text.includes("contact Ashok") ||
            text.includes("contact");

        const words = text.split(" ");
        let index = 0;

        const interval = setInterval(() => {
            if (index < words.length) {
                div.innerText += (index === 0 ? "" : " ") + words[index];
                index++;
                scrollBottom();
            } else {
                clearInterval(interval);

                // Append clickable link AFTER typing
                if (needsLink) {
                    const br = document.createElement("br");

                    const link = document.createElement("a");
                    link.href = linkedinURL;
                    link.target = "_blank";
                    link.rel = "noopener noreferrer";
                    link.innerText = "Open LinkedIn";
                    link.style.color = "#2563eb";
                    link.style.textDecoration = "underline";
                    link.style.fontWeight = "600";

                    div.appendChild(br);
                    div.appendChild(link);
                }

                isTyping = false;
                scrollBottom();
            }
        }, 70);
    }

    function getAnswer(question) {
        const q = question.toLowerCase().trim();

        if (q.includes("carefinder") || q.includes("about")) return answers["what is carefinder"];
        if (q.includes("start") || q.includes("state") || q.includes("begin")) return answers["how to start"];
        if (q.includes("recommendation") || q.includes("top hospital")) return answers["recommendations"];
        if (q.includes("compare")) return answers["compare"];
        if (q.includes("detail") || q.includes("single hospital")) return answers["hospital detail"];
        if (q.includes("data") || q.includes("synthea")) return answers["data source"];
        if (q.includes("predict") || q.includes("forecast") || q.includes("model") || q.includes("pkl")) return answers["prediction"];
        if (q.includes("insurance") || q.includes("payer") || q.includes("coverage")) return answers["insurance"];
        if (q.includes("contact") || q.includes("linkedin")) return answers["contact"];

        return "I could not find that answer in the CareFinder knowledge base. Please contact Ashok Medasani on LinkedIn:";
    }

    function sendMessage(text) {
        if (!text.trim() || isTyping) return;

        addUserMessage(text);
        input.value = "";

        setTimeout(() => {
            addBotTypingMessage(getAnswer(text));
        }, 400);
    }

    botBtn.addEventListener("click", function () {
        botBox.classList.toggle("open");

        if (!started) {
            started = true;

            setTimeout(() => {
                addBotTypingMessage(
                    "Hi, welcome to CareFinder. I can help you understand what this application does, how to start, what each page means, and how recommendations, comparison, and predictions work."
                );
            }, 300);
        }
    });

    closeBtn.addEventListener("click", function () {
        botBox.classList.remove("open");
    });

    sendBtn.addEventListener("click", function () {
        sendMessage(input.value);
    });

    input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            sendMessage(input.value);
        }
    });

    faqButtons.forEach(button => {
        button.addEventListener("click", function () {
            const question = this.getAttribute("data-question");
            sendMessage(question);
        });
    });
});
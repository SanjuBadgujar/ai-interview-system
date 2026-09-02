import { useState, useEffect } from "react";

export default function TypewriterText({ text, active, speed = 25 }) {
  const [displayed, setDisplayed] = useState("");

  useEffect(() => {
    if (!text) {
      setDisplayed("");
      return;
    }
    if (!active) {
      setDisplayed(text);
      return;
    }

    setDisplayed("");
    let i = 0;
    const timer = setInterval(() => {
      i++;
      if (i >= text.length) {
        clearInterval(timer);
        setDisplayed(text);
      } else {
        setDisplayed(text.slice(0, i));
      }
    }, speed);

    return () => clearInterval(timer);
  }, [text, active, speed]);

  return (
    <>
      {displayed}
      {active && <span className="typing-cursor" />}
    </>
  );
}

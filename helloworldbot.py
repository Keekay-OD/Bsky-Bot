from time import sleep
from polybot import Bot
import logging
from groq import Groq
import os

class TechNewsBot(Bot):
    def __init__(self, name):
        super().__init__(name)
        # Initialize Groq client
        self.groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        self.system_prompt = """You are a tech news and facts bot. Generate interesting, 
        engaging posts about technology, gaming, software, hardware, or tech history. 
        Keep posts informative yet concise, under 300 characters. Include only verified, 
        factual information. Format as a single post without hashtags or citations."""

    def generate_post(self):
        try:
            chat_completion = self.groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": "Generate a single interesting tech fact or news update."}
                ],
                model="llama-3.1-70b-versatile",
                max_tokens=100,
                temperature=0.7
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            self.log.error(f"Error generating post: {e}")
            return None

    def main(self):
        while True:
            try:
                # Generate a new post using Groq
                post = self.generate_post()
                
                if post:
                    # Ensure post meets length requirements
                    if len(post) > 300:
                        post = post[:297] + "..."
                    
                    # Post to Bluesky
                    self.post(post)
                    self.log.info(f"Posted: {post}")
                else:
                    self.log.warning("Failed to generate post, will retry in 5 minutes")
                    sleep(300)
                    continue

                # Wait for an hour before next post
                sleep(3600)

            except Exception as e:
                self.log.error(f"Error in main loop: {e}")
                sleep(60)  # If there's an error, wait 1 minute before retrying

if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(module)s: %(message)s",
    )

    # Make sure GROQ_API_KEY is set in environment
    if not os.getenv('GROQ_API_KEY'):
        raise ValueError("GROQ_API_KEY environment variable must be set")

    TechNewsBot('technewsbot').run()
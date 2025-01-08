from time import sleep
from polybot import Bot
import logging
from groq import Groq
import os
import json
from datetime import datetime
import hashlib

class TechNewsBot(Bot):
    def __init__(self, name):
        super().__init__(name)
        # Initialize Groq client
        self.groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))
        self.system_prompt = """You are a tech news and facts bot. Generate interesting, 
        engaging posts about technology, gaming, software, hardware, or tech history. 
        Keep posts informative yet concise, under 300 characters. Include only verified, 
        factual information. Format as a single post without hashtags or citations."""
        
        # Initialize posts history
        self.history_file = 'post_history.json'
        self.post_history = self.load_post_history()

    def load_post_history(self):
        """Load post history from JSON file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            return {'posts': []}
        except Exception as e:
            self.log.error(f"Error loading post history: {e}")
            return {'posts': []}

    def save_post_history(self):
        """Save post history to JSON file"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.post_history, f, indent=2)
        except Exception as e:
            self.log.error(f"Error saving post history: {e}")

    def is_duplicate(self, post):
        """Check if post is too similar to previous posts"""
        # Create a hash of the post content
        post_hash = hashlib.md5(post.lower().encode()).hexdigest()
        
        # Check if this exact hash exists in history
        for historical_post in self.post_history['posts']:
            if historical_post['hash'] == post_hash:
                return True
            
        return False

    def add_to_history(self, post):
        """Add post to history"""
        post_data = {
            'content': post,
            'hash': hashlib.md5(post.lower().encode()).hexdigest(),
            'timestamp': datetime.now().isoformat()
        }
        self.post_history['posts'].append(post_data)
        
        # Keep only last 1000 posts in history
        if len(self.post_history['posts']) > 1000:
            self.post_history['posts'] = self.post_history['posts'][-1000:]
            
        self.save_post_history()

    def generate_post(self):
        max_attempts = 5  # Maximum number of attempts to generate unique content
        
        for attempt in range(max_attempts):
            try:
                chat_completion = self.groq_client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": "Generate a unique tech fact or news update different from common knowledge."}
                    ],
                    model="llama-3.1-70b-versatile",
                    max_tokens=100,
                    temperature=0.9  # Increased temperature for more variety
                )
                
                post = chat_completion.choices[0].message.content.strip()
                
                if post and not self.is_duplicate(post):
                    return post
                else:
                    self.log.info(f"Generated duplicate content, attempt {attempt + 1} of {max_attempts}")
                    
            except Exception as e:
                self.log.error(f"Error generating post: {e}")
                return None
                
        self.log.warning("Failed to generate unique content after maximum attempts")
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
                    self.log.warning("Positng again in 20 minutes")

                    # Add to history after successful posting
                    self.add_to_history(post)
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
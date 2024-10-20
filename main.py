import os
import sys
import json
import importlib
import traceback
from flask import Flask, Blueprint, request, send_from_directory, render_template_string, jsonify
from threading import Thread
from time import sleep
from litellm import completion, supports_function_calling

# Configuration
MODEL_NAME = os.environ.get('LITELLM_MODEL', 'gpt-4')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, 'projects')
LOG_FILE = "flask_app_builder_log.json"

app = Flask(__name__)

# Initialize progress tracking
progress = {
    "status": "idle",
    "iteration": 0,
    "max_iterations": 50,
    "output": "",
    "completed": False
}

def create_directory(path):
    if not os.path.exists(path):
        os.makedirs(path)
        return f"Created directory: {path}"
    return f"Directory already exists: {path}"

def create_file(path, content):
    try:
        with open(path, 'x') as f:
            f.write(content)
        return f"Created file: {path}"
    except FileExistsError:
        with open(path, 'w') as f:
            f.write(content)
        return f"Updated file: {path}"
    except Exception as e:
        return f"Error creating/updating file {path}: {e}"

def update_file(path, content):
    try:
        with open(path, 'w') as f:
            f.write(content)
        return f"Updated file: {path}"
    except Exception as e:
        return f"Error updating file {path}: {e}"

def fetch_code(file_path):
    try:
        with open(file_path, 'r') as f:
            code = f.read()
        return code
    except Exception as e:
        return f"Error fetching code from {file_path}: {e}"

def task_completed():
    progress["status"] = "completed"
    progress["completed"] = True
    return "Task marked as completed."

def log_to_file(history_dict):
    try:
        with open(LOG_FILE, 'w') as log_file:
            json.dump(history_dict, log_file, indent=4)
    except Exception as e:
        pass  # Silent fail

def get_projects():
    projects = []
    if os.path.exists(PROJECTS_DIR):
        for project in os.listdir(PROJECTS_DIR):
            project_path = os.path.join(PROJECTS_DIR, project)
            if os.path.isdir(project_path):
                projects.append(project)
    return projects

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        user_input = request.form.get('user_input')
        project_name = request.form.get('project_name')
        if not project_name:
            return render_template_string('''
                <h1>Error</h1>
                <p>Project name is required.</p>
                <a href="/">Back to Home</a>
            ''')
        
        project_dir = os.path.join(PROJECTS_DIR, project_name)
        create_directory(project_dir)
        
        progress["status"] = "running"
        progress["iteration"] = 0
        progress["output"] = ""
        progress["completed"] = False
        thread = Thread(target=run_main_loop, args=(user_input, project_dir))
        thread.start()
        return render_template_string('''
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Progress - {{ project_name }}</title>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }
                    h1 { color: #2c3e50; }
                    #progress { background-color: #f9f9f9; border: 1px solid #ddd; padding: 15px; border-radius: 5px; }
                    #refresh-btn { display: none; background-color: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; }
                    #refresh-btn:hover { background-color: #2980b9; }
                </style>
            </head>
            <body>
                <h1>Progress - {{ project_name }}</h1>
                <div id="progress">{{ progress_output }}</div>
                <button id="refresh-btn" onclick="location.reload();">Refresh Page</button>
                <script>
                    setInterval(function() {
                        fetch('/progress')
                        .then(response => response.json())
                        .then(data => {
                            document.getElementById('progress').innerHTML = data.output;
                            if (data.completed) {
                                document.getElementById('refresh-btn').style.display = 'block';
                            }
                        });
                    }, 2000);
                </script>
            </body>
            </html>
        ''', progress_output=progress["output"], project_name=project_name)
    else:
        projects = get_projects()
        return render_template_string('''
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Flask App Builder</title>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }
                    h1 { color: #2c3e50; }
                    form { background-color: #f9f9f9; border: 1px solid #ddd; padding: 20px; border-radius: 5px; }
                    label { display: block; margin-bottom: 5px; }
                    input[type="text"], textarea { width: 100%; padding: 8px; margin-bottom: 10px; border: 1px solid #ddd; border-radius: 4px; }
                    input[type="submit"] { background-color: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; }
                    input[type="submit"]:hover { background-color: #2980b9; }
                    .project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; margin-top: 20px; }
                    .project-card { background-color: #f9f9f9; border: 1px solid #ddd; padding: 15px; border-radius: 5px; text-align: center; }
                </style>
            </head>
            <body>
                <h1>Flask App Builder</h1>
                <form method="post">
                    <label for="project_name">Project Name:</label>
                    <input type="text" id="project_name" name="project_name" required>
                    <label for="user_input">Describe the Flask app you want to create:</label>
                    <textarea id="user_input" name="user_input" rows="6" required></textarea>
                    <input type="submit" value="Create Project">
                </form>
                <h2>Existing Projects</h2>
                <div class="project-grid">
                    {% for project in projects %}
                        <div class="project-card">
                            <h3>{{ project }}</h3>
                            <a href="/project/{{ project }}">View Project</a>
                        </div>
                    {% endfor %}
                </div>
            </body>
            </html>
        ''', projects=projects)

@app.route('/project/<project_name>')
def view_project(project_name):
    project_dir = os.path.join(PROJECTS_DIR, project_name)
    if not os.path.exists(project_dir):
        return "Project not found", 404
    
    files = []
    for root, dirs, filenames in os.walk(project_dir):
        for filename in filenames:
            files.append(os.path.relpath(os.path.join(root, filename), project_dir))
    
    return render_template_string('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{{ project_name }} - Files</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }
                h1 { color: #2c3e50; }
                ul { list-style-type: none; padding: 0; }
                li { margin-bottom: 10px; }
                a { color: #3498db; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>{{ project_name }} - Files</h1>
            <ul>
                {% for file in files %}
                    <li><a href="/project/{{ project_name }}/file/{{ file }}">{{ file }}</a></li>
                {% endfor %}
            </ul>
            <a href="/">Back to Home</a>
        </body>
        </html>
    ''', project_name=project_name, files=files)

@app.route('/project/<project_name>/file/<path:filename>')
def view_file(project_name, filename):
    file_path = os.path.join(PROJECTS_DIR, project_name, filename)
    if not os.path.exists(file_path):
        return "File not found", 404
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    return render_template_string('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{{ filename }} - {{ project_name }}</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }
                h1 { color: #2c3e50; }
                pre { background-color: #f9f9f9; border: 1px solid #ddd; padding: 15px; border-radius: 5px; overflow-x: auto; }
                a { color: #3498db; text-decoration: none; }
                a:hover { text-decoration: underline; }
            </style>
        </head>
        <body>
            <h1>{{ filename }}</h1>
            <pre><code>{{ content }}</code></pre>
            <a href="/project/{{ project_name }}">Back to Project Files</a>
        </body>
        </html>
    ''', filename=filename, project_name=project_name, content=content)

@app.route('/progress')
def get_progress():
    return jsonify(progress)

# Available functions for the LLM
available_functions = {
    "create_directory": create_directory,
    "create_file": create_file,
    "update_file": update_file,
    "fetch_code": fetch_code,
    "task_completed": task_completed
}

# Define the tools for function calling
tools = [
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Creates a new directory at the specified path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The directory path to create."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Creates or updates a file at the specified path with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to create or update."
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write into the file."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_file",
            "description": "Updates an existing file at the specified path with the new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to update."
                    },
                    "content": {
                        "type": "string",
                        "description": "The new content to write into the file."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_code",
            "description": "Retrieves the code from the specified file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The file path to fetch the code from."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "task_completed",
            "description": "Indicates that the assistant has completed the task.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

def run_main_loop(user_input, project_dir):
    history_dict = {"iterations": []}

    if not supports_function_calling(MODEL_NAME):
        progress["status"] = "error"
        progress["output"] = "Model does not support function calling."
        progress["completed"] = True
        return "Model does not support function calling."

    max_iterations = progress["max_iterations"]
    iteration = 0

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert Flask developer tasked with building a complete, production-ready Flask application based on the user's description. "
                "Before coding, carefully plan out all the files, routes, templates, and static assets needed. "
                f"All files should be created within the project directory: {project_dir}\n"
                "Follow these steps:\n"
                "1. **Understand the Requirements**: Analyze the user's input to fully understand the application's functionality and features.\n"
                "2. **Plan the Application Structure**: List all the routes, templates, and static files that need to be created. Consider how they interact.\n"
                "3. **Implement Step by Step**: For each component, use the provided tools to create directories, files, and write code. Ensure each step is thoroughly completed before moving on.\n"
                "4. **Review and Refine**: Use `fetch_code` to review the code you've written. Update files if necessary using `update_file`.\n"
                "5. **Ensure Completeness**: Do not leave any placeholders or incomplete code. All functions, routes, and templates must be fully implemented and ready for production.\n"
                "6. **Finalize**: Once everything is complete and thoroughly tested, call `task_completed()` to finish.\n\n"
                "Constraints and Notes:\n"
                f"- The application files must be structured within the project directory: {project_dir}\n"
                "- Routes should be modular and placed inside a `routes/` directory as separate Python files.\n"
                "- Templates should be placed in a `templates/` directory.\n"
                "- Static files (CSS, JS, images) should be placed in a `static/` directory.\n"
                "- Do not use placeholders like 'Content goes here'. All code should be complete and functional.\n"
                "- Do not ask the user for additional input; infer any necessary details to complete the application.\n"
                "- Ensure all routes are properly linked and that templates include necessary CSS and JS files.\n"
                "- Handle any errors internally and attempt to resolve them before proceeding.\n\n"
                "Available Tools:\n"
                "- `create_directory(path)`: Create a new directory.\n"
                "- `create_file(path, content)`: Create or overwrite a file with content.\n"
                "- `update_file(path, content)`: Update an existing file with new content.\n"
                "- `fetch_code(file_path)`: Retrieve the code from a file for review.\n"
                "- `task_completed()`: Call this when the application is fully built and ready.\n\n"
                "Remember to think carefully at each step, ensuring the application is complete, functional, and meets the user's requirements."
            )
        },
        {"role": "user", "content": user_input},
        {"role": "system", "content": f"History:\n{json.dumps(history_dict, indent=2)}"}
    ]

    output = ""

    while iteration < max_iterations:
        progress["iteration"] = iteration + 1
        current_iteration = {
            "iteration": iteration + 1,
            "actions": [],
            "llm_responses": [],
            "tool_results": [],
            "errors": []
        }
        history_dict['iterations'].append(current_iteration)

        try:
            response = completion(
                model=MODEL_NAME,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )

            if not response.choices[0].message:
                error = response.get('error', 'Unknown error')
                current_iteration['errors'].append({'action': 'llm_completion', 'error': error})
                log_to_file(history_dict)
                sleep(5)
                iteration += 1
                continue

            response_message = response.choices[0].message
            content = response_message.content or ""
            current_iteration['llm_responses'].append(content)

            output += f"\n<h3>Iteration {iteration + 1}:</h3>\n"

            tool_calls = response_message.tool_calls

            if tool_calls:
                output += "<strong>Tool Call:</strong>\n<p>" + content + "</p>\n"
                messages.append(response_message)

                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_to_call = available_functions.get(function_name)

                    if not function_to_call:
                        error_message = f"Tool '{function_name}' is not available."
                        current_iteration['errors'].append({
                            'action': f'tool_call_{function_name}',
                            'error': error_message,
                            'traceback': 'No traceback available.'
                        })
                        continue

                    try:
                        function_args = json.loads(tool_call.function.arguments)

                        function_response = function_to_call(**function_args)

                        current_iteration['tool_results'].append({
                            'tool': function_name,
                            'result': function_response
                        })

                        output += f"<strong>Tool Result ({function_name}):</strong>\n<p>{function_response}</p>\n"

                        messages.append(
                            {"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": function_response}
                        )

                        if function_name == "task_completed":
                            progress["status"] = "completed"
                            progress["completed"] = True
                            output += "\n<h2>COMPLETE</h2>\n"
                            progress["output"] = output
                            log_to_file(history_dict)
                            return output

                    except Exception as tool_error:
                        error_message = f"Error executing {function_name}: {tool_error}"
                        current_iteration['errors'].append({
                            'action': f'tool_call_{function_name}',
                            'error': error_message,
                            'traceback': traceback.format_exc()
                        })

                second_response = completion(
                    model=MODEL_NAME,
                    messages=messages
                )
                if second_response.choices and second_response.choices[0].message:
                    second_response_message = second_response.choices[0].message
                    content = second_response_message.content or ""
                    current_iteration['llm_responses'].append(content)
                    output += "<strong>LLM Response:</strong>\n<p>" + content + "</p>\n"
                    messages.append(second_response_message)
                else:
                    error = second_response.get('error', 'Unknown error in second LLM response.')
                    current_iteration['errors'].append({'action': 'second_llm_completion', 'error': error})

            else:
                output += "<strong>LLM Response:</strong>\n<p>" + content + "</p>\n"
                messages.append(response_message)

            progress["output"] = output

        except Exception as e:
            error = str(e)
            current_iteration['errors'].append({
                'action': 'main_loop',
                'error': error,
                'traceback': traceback.format_exc()
            })

        iteration += 1
        log_to_file(history_dict)
        sleep(2)

    if iteration >= max_iterations:
        progress["status"] = "completed"

    progress["completed"] = True
    progress["status"] = "completed"

    return output

if __name__ == '__main__':
    create_directory(PROJECTS_DIR)
    app.run(host='0.0.0.0', port=8080)
from flask import Flask, render_template, url_for, request, redirect

main = Flask(__name__)

@main.route('/')
def homepage():
    return render_template('homepage.html')

@main.route('/avail')
def avail():
    return render_template('avail.html')

@main.route('/form')
def form():
    return render_template('form.html')

if __name__ == '__main__':
    main.run(debug=True)

import { web_archive, without_origin } from "@lib/util";
import html_template_string from "@lib/weekly_email.html.handlebars?raw";
import plain_template_string from "@lib/weekly_email.txt.handlebars?raw";
import Handlebars from "handlebars";

Handlebars.registerHelper('without_origin', without_origin);
Handlebars.registerHelper('web_archive', url => web_archive(url));

export const html_template = Handlebars.compile(html_template_string, { strict: true });
export const plain_template = Handlebars.compile(plain_template_string, { strict: true });

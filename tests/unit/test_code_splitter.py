import unittest
from minder.chunking.code_splitter import CodeSplitter
class TestCodeSplitter(unittest.TestCase):
    def setUp(self):
        self.splitter = CodeSplitter()

    def test_split_python(self):
        code = """import os
from typing import List

def calculate_sum(a: int, b: int) -> int:
    return a + b

class MathService:
    def multiply(self, x: int, y: int) -> int:
        return x * y
"""
        chunks = self.splitter.split(code, language="python")
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].symbol_name, "calculate_sum")
        self.assertIn("import os", chunks[0].content)
        self.assertEqual(chunks[1].symbol_name, "MathService")
        self.assertEqual(chunks[1].start_line, 7)

    def test_split_typescript(self):
        code = """import { Request, Response } from 'express';

export interface UserDTO {
    id: string;
    email: string;
}

export function handleLogin(req: Request, res: Response) {
    const { email } = req.body;
    res.json({ ok: true });
}
"""
        chunks = self.splitter.split(code, language="typescript")
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(any("interface UserDTO" in c.content for c in chunks))
        self.assertTrue(any("function handleLogin" in c.content for c in chunks))

    def test_split_golang(self):
        code = """package auth

import "net/http"

type LoginRequest struct {
    Email string `json:"email"`
}

func HandleLogin(w http.ResponseWriter, r *http.Request) {
    w.Write([]byte("ok"))
}
"""
        chunks = self.splitter.split(code, language="go")
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(any("type LoginRequest struct" in c.content for c in chunks))
        self.assertTrue(any("func HandleLogin" in c.content for c in chunks))

    def test_split_rust(self):
        code = """pub struct User {
    pub id: u64,
    pub name: String,
}

impl User {
    pub fn new(id: u64, name: String) -> Self {
        Self { id, name }
    }
}
"""
        chunks = self.splitter.split(code, language="rust")
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(any("pub struct User" in c.content for c in chunks))
        self.assertTrue(any("impl User" in c.content for c in chunks))

    def test_split_java(self):
        code = """package com.example;

public class UserService {
    public User findUser(String id) {
        return new User(id);
    }
}
"""
        chunks = self.splitter.split(code, language="java")
        self.assertGreaterEqual(len(chunks), 1)
        self.assertIn("class UserService", chunks[0].content)

    def test_split_config_and_markup(self):
        # YAML
        yaml_code = """server:
  port: 8080
  host: 0.0.0.0

database:
  url: postgres://localhost:5432
  pool_size: 10
"""
        yaml_chunks = self.splitter.split(yaml_code, language="yaml")
        self.assertGreaterEqual(len(yaml_chunks), 1)

        # JSON
        json_code = '{\n  "name": "minder",\n  "version": "1.0.0"\n}'
        json_chunks = self.splitter.split(json_code, language="json")
        self.assertEqual(len(json_chunks), 1)

if __name__ == "__main__":
    unittest.main()

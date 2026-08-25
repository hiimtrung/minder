import unittest
import uuid
from src.minder.application.contracts.extractor import ContractExtractor

class TestContractExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = ContractExtractor()
        self.ws_id = uuid.uuid4()
        self.repo_id = uuid.uuid4()

    def test_extract_python_fastapi_and_pydantic(self):
        code = """from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/api/v1/auth/login")
async def login(req: LoginRequest):
    return {"token": "xyz"}
"""
        contracts = self.extractor.extract(
            code=code,
            file_path="src/auth/routes.py",
            language="python",
            workspace_id=self.ws_id,
            repo_id=self.repo_id,
        )
        self.assertEqual(len(contracts), 2)
        identifiers = {c.identifier for c in contracts}
        self.assertIn("POST /api/v1/auth/login", identifiers)
        self.assertIn("LoginRequest", identifiers)

    def test_extract_typescript_express_and_interface(self):
        code = """import { Router } from 'express';

export interface UserProfileDTO {
    id: string;
    email: string;
    role: string;
}

const router = Router();

router.get('/api/v1/users/:id', async (req, res) => {
    res.json({ id: req.params.id });
});
"""
        contracts = self.extractor.extract(
            code=code,
            file_path="src/routes/user.ts",
            language="typescript",
            workspace_id=self.ws_id,
            repo_id=self.repo_id,
        )
        self.assertEqual(len(contracts), 2)
        identifiers = {c.identifier for c in contracts}
        self.assertIn("GET /api/v1/users/:id", identifiers)
        self.assertIn("UserProfileDTO", identifiers)

    def test_extract_golang_gin_and_struct(self):
        code = """package handlers

type CreateOrderRequest struct {
    ItemID   string  `json:"item_id"`
    Quantity int     `json:"quantity"`
    Price    float64 `json:"price"`
}

func RegisterRoutes(r *gin.Engine) {
    r.POST("/api/v1/orders", CreateOrderHandler)
}
"""
        contracts = self.extractor.extract(
            code=code,
            file_path="internal/orders/handler.go",
            language="go",
            workspace_id=self.ws_id,
            repo_id=self.repo_id,
        )
        self.assertEqual(len(contracts), 2)
        identifiers = {c.identifier for c in contracts}
        self.assertIn("POST /api/v1/orders", identifiers)
        self.assertIn("CreateOrderRequest", identifiers)

    def test_extract_protobuf(self):
        code = """syntax = "proto3";

package payment.v1;

message ProcessPaymentRequest {
    string order_id = 1;
    double amount = 2;
}

service PaymentService {
    rpc ProcessPayment(ProcessPaymentRequest) returns (PaymentResponse);
}
"""
        contracts = self.extractor.extract(
            code=code,
            file_path="proto/payment.proto",
            language="protobuf",
            workspace_id=self.ws_id,
            repo_id=self.repo_id,
        )
        self.assertEqual(len(contracts), 2)
        identifiers = {c.identifier for c in contracts}
        self.assertIn("ProcessPaymentRequest", identifiers)
        self.assertIn("rpc ProcessPayment", identifiers)

if __name__ == "__main__":
    unittest.main()
